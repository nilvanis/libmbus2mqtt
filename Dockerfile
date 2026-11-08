# Stage 1: Build the pinned libmbus sources with the shared TCP timeout patch.
FROM debian:bookworm-slim AS libmbus-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git build-essential libtool libltdl-dev autoconf automake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY src/libmbus2mqtt/resources/libmbus.env ./libmbus.env
COPY src/libmbus2mqtt/resources/libmbus-tcp-timeout.patch ./libmbus-tcp-timeout.patch
RUN . ./libmbus.env && \
    git init libmbus && \
    cd libmbus && \
    git fetch --depth 1 "$LIBMBUS_REPO" "$LIBMBUS_COMMIT" && \
    git checkout --detach "$LIBMBUS_COMMIT" && \
    git apply --check ../libmbus-tcp-timeout.patch && \
    git apply ../libmbus-tcp-timeout.patch && \
    ./build.sh && \
    make install DESTDIR=/install

# Stage 2: Install the project and runtime dependencies from uv.lock.
FROM python:3.14.6-slim-bookworm AS python-builder
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable

# Stage 3: Runtime image.
FROM python:3.14.6-slim-bookworm
LABEL org.opencontainers.image.title="libmbus2mqtt"
LABEL org.opencontainers.image.description="M-Bus to MQTT bridge with Home Assistant integration"
LABEL org.opencontainers.image.source="https://github.com/nilvanis/libmbus2mqtt"

RUN apt-get update && apt-get install -y --no-install-recommends libxml2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=libmbus-builder /install/usr/local/bin/mbus-* /usr/local/bin/
COPY --from=libmbus-builder /install/usr/local/lib/libmbus* /usr/local/lib/
COPY --from=libmbus-builder /build/libmbus.env /usr/local/share/libmbus2mqtt/libmbus.env
RUN ldconfig

COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Runtime identity, pinned so existing volumes keep working across base images.
# The entrypoint starts as root only to give /data to PUID:PGID (defaults below),
# grant mapped serial device groups and drop privileges; with `user:` it runs the
# app directly.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --gid "$APP_GID" libmbus2mqtt && \
    useradd --uid "$APP_UID" --gid "$APP_GID" --groups dialout --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin libmbus2mqtt && \
    install -d -o "$APP_UID" -g "$APP_GID" -m 0750 \
        /data /data/config /data/log /data/templates
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
# CLI defaults are the native /etc + /var/lib paths; every command in the image
# (run, scan, config init, ...) uses /data instead.
ENV PUID=$APP_UID \
    PGID=$APP_GID \
    LIBMBUS2MQTT_CONFIG=/data/config/config.yaml \
    LIBMBUS2MQTT_DATA_DIR=/data
VOLUME ["/data"]
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["run"]
