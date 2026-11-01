# syntax=docker/dockerfile:1

# --- Stage 1: render the static site with Django -------------------------
FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY manage.py pyproject.toml ./
COPY filnews ./filnews
# The JSON database and thumbnails are baked into the image.
COPY data ./data

ARG SITE_URL=https://www.filnews.fr
ENV SITE_URL=${SITE_URL} \
    DJANGO_DEBUG=0

RUN python manage.py build_site --output /app/dist \
 && find /app/dist -type f \( -name '*.html' -o -name '*.css' -o -name '*.js' \
        -o -name '*.xml' -o -name '*.txt' -o -name '*.svg' -o -name '*.json' \) \
        -print0 | xargs -0 -P "$(nproc)" -n 200 gzip -9 -k

# --- Stage 2: serve it with nginx (non-root) ------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://127.0.0.1:8000/ || exit 1
