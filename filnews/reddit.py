"""Minimal Reddit OAuth2 client.

Authentication strategy:
- If a refresh token was obtained through the authorization-code flow
  (`/auth/reddit/login` -> `/auth/reddit/callback`), it is used.
- Otherwise the client falls back to application-only OAuth
  (`client_credentials`), which is enough to read public subreddits.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://www.reddit.com/api/v1/authorize"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"  # noqa: S105
API_BASE = "https://oauth.reddit.com"
SCOPES = "identity read"
PAGE_SIZE = 100
MAX_PAGES = 10  # Reddit listings stop around 1000 items anyway.


class RedditError(RuntimeError):
    pass


class RedditClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        redirect_uri: str,
        token_file: Path,
        session: requests.Session | None = None,
    ):
        if not client_id or not client_secret:
            raise RedditError(
                "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set "
                "(see .env.example)."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = Path(token_file)
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self._access_token: str | None = None
        self._expires_at = 0.0

    @classmethod
    def from_settings(cls, session: requests.Session | None = None) -> RedditClient:
        return cls(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT,
            redirect_uri=settings.REDDIT_REDIRECT_URI,
            token_file=settings.REDDIT_TOKEN_FILE,
            session=session,
        )

    # --- Authorization-code flow ------------------------------------------

    def authorize_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": self.redirect_uri,
            "duration": "permanent",
            "scope": SCOPES,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> None:
        payload = self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }
        )
        refresh_token = payload.get("refresh_token")
        if not refresh_token:
            raise RedditError("Reddit did not return a refresh token.")
        self._save_refresh_token(refresh_token)
        self._remember(payload)

    def _save_refresh_token(self, refresh_token: str) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps({"refresh_token": refresh_token}))
        self.token_file.chmod(0o600)

    def _load_refresh_token(self) -> str | None:
        if not self.token_file.is_file():
            return None
        return json.loads(self.token_file.read_text()).get("refresh_token")

    # --- Access token ------------------------------------------------------

    def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        response = self.session.post(
            TOKEN_URL,
            data=data,
            auth=(self.client_id, self.client_secret),
            timeout=settings.HTTP_TIMEOUT,
        )
        if response.status_code != 200:
            raise RedditError(f"Token request failed ({response.status_code}).")
        payload = response.json()
        if "error" in payload:
            raise RedditError(f"Token request failed: {payload['error']}")
        return payload

    def _remember(self, payload: dict[str, Any]) -> None:
        self._access_token = payload["access_token"]
        # Refresh one minute before actual expiry.
        self._expires_at = time.monotonic() + int(payload.get("expires_in", 3600)) - 60

    def access_token(self) -> str:
        if self._access_token and time.monotonic() < self._expires_at:
            return self._access_token
        refresh_token = self._load_refresh_token()
        if refresh_token:
            data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        else:
            data = {"grant_type": "client_credentials"}
        self._remember(self._token_request(data))
        return self._access_token

    # --- API ---------------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.access_token()}"},
            timeout=settings.HTTP_TIMEOUT,
        )
        if response.status_code != 200:
            raise RedditError(f"GET {path} failed ({response.status_code}).")
        return response.json()

    def top_posts(self, subreddit: str, period: str) -> Iterator[dict[str, Any]]:
        """Yield posts of `/r/<subreddit>/top` for `period`, best score first."""
        after = None
        for _ in range(MAX_PAGES):
            params = {"t": period, "limit": PAGE_SIZE, "raw_json": 1}
            if after:
                params["after"] = after
            listing = self.get(f"/r/{subreddit}/top", params)["data"]
            for child in listing["children"]:
                yield child["data"]
            after = listing.get("after")
            if not after:
                return

    def posts_by_id(self, ids: Iterable[str]) -> Iterator[dict[str, Any]]:
        """Yield the current data of the given posts (`/api/info`, 100 per call).

        Deleted posts that Reddit no longer knows are silently missing.
        """
        ids = list(ids)
        for offset in range(0, len(ids), PAGE_SIZE):
            chunk = ids[offset : offset + PAGE_SIZE]
            params = {
                "id": ",".join(f"t3_{post_id}" for post_id in chunk),
                "raw_json": 1,
            }
            listing = self.get("/api/info", params)["data"]
            for child in listing["children"]:
                yield child["data"]
