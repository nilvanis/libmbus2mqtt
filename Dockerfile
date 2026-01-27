# Multi-stage Dockerfile for libmbus2mqtt
# Stage 1: Build libmbus from source
FROM debian:bookworm-slim AS libmbus-builder

RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libtool \
    autoconf \
    automake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Clone and build libmbus
# Adjust TCP timeout from 4 seconds to 1 second
RUN git clone --depth 1 https://github.com/rscada/libmbus.git && \
    cd libmbus && \
    sed -i 's/^static int tcp_timeout_sec = 4;$/static int tcp_timeout_sec = 1;/' mbus/mbus-tcp.c && \
    ./build.sh && \
    make install DESTDIR=/install

# Stage 2: Build Python package
FROM python:3.11-slim-bookworm AS python-builder

WORKDIR /app

# Install uv for faster dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build wheel
RUN uv build --wheel

# Stage 3: Runtime image
FROM python:3.11-slim-bookworm

# Labels
LABEL org.opencontainers.image.title="libmbus2mqtt"
LABEL org.opencontainers.image.description="M-Bus to MQTT bridge with Home Assistant integration"
LABEL org.opencontainers.image.source="https://github.com/nilvanis/libmbus2mqtt"

# Install runtime dependencies for libmbus
RUN apt-get update && apt-get install -y \
    libxml2 \
    && rm -rf /var/lib/apt/lists/*

# Copy libmbus binaries and libraries from builder
COPY --from=libmbus-builder /install/usr/local/bin/mbus-* /usr/local/bin/
COPY --from=libmbus-builder /install/usr/local/lib/libmbus* /usr/local/lib/

# Update library cache
RUN ldconfig

# Copy Python wheel and install
COPY --from=python-builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

# Create data directory structure
RUN mkdir -p /data/config /data/templates

# Set environment variable for config location
ENV LIBMBUS2MQTT_CONFIG=/data/config/config.yaml

# Volume for configuration and templates
VOLUME ["/data"]

# Run as non-root user
RUN useradd -r -s /bin/false libmbus2mqtt && \
    chown -R libmbus2mqtt:libmbus2mqtt /data
USER libmbus2mqtt

ENTRYPOINT ["libmbus2mqtt"]
CMD ["run"]
