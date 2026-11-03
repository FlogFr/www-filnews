from collections import Counter

from django.core.management.base import BaseCommand

from filnews.media import is_accepted
from filnews.store import get_store


class Command(BaseCommand):
    help = (
        "List the stored news whose site is refused by the media policy "
        "(filnews/media.py); delete them with --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Delete them (and their thumbnail)."
        )

    def handle(self, *args, apply, **options):
        store = get_store()
        refused = [news for news in store.all() if not is_accepted(news.domain)]
        domains = Counter(news.domain for news in refused)
        for domain, count in domains.most_common():
            self.stdout.write(f"{count:6d}  {domain}")
        self.stdout.write(
            f"{len(refused)} news on {len(domains)} refused sites "
            f"(out of {len(store)})."
        )
        if not apply:
            self.stdout.write("Dry run: nothing deleted (use --apply).")
            return
        with store.transaction():
            for news in refused:
                store.remove(news.id)
        self.stdout.write(self.style.SUCCESS(f"Deleted {len(refused)} news."))
