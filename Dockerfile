FROM python:3.12-slim AS build
WORKDIR /build
COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    AARR_DATA_DIR=/config \
    AARR_HOST=0.0.0.0 \
    AARR_PORT=8686
COPY --from=build /opt/venv /opt/venv
# Default uid/gid 1000; override with `user:` / `--user` to match media file ownership.
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin aarr \
    && mkdir /config && chown 1000:1000 /config
USER 1000:1000
VOLUME /config
EXPOSE 8686
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/v1/health' % os.environ['AARR_PORT'], timeout=3)"]
CMD ["aarr"]
