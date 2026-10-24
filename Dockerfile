# syntax=docker/dockerfile:1.7
FROM python:3.12.8-slim-bookworm AS build
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_HOST=0.0.0.0 APP_PORT=8080
WORKDIR /app
COPY --from=build /install /usr/local
COPY core ./core
COPY domains ./domains
COPY apps ./apps
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app && chown -R app /app
USER app
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200 else 1)"
CMD ["python", "-m", "apps.web"]
