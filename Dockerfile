# ==========================================
# Stage 1: Build virtual env and dependencies
# ==========================================
FROM python:3.13-slim AS builder

WORKDIR /build

# Support proxy CA certificate and HTTP/HTTPS proxies if they are set in the environment
ARG PROXY_CA_CERT_B64
ARG http_proxy
ARG https_proxy
ARG no_proxy
ARG TARGETARCH

# Setup HTTPS sources for Debian, trust the proxy certificate if provided, and install upx-ucl (with caching)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    if [ -n "$PROXY_CA_CERT_B64" ]; then \
        echo "Trusting custom proxy CA certificate..." && \
        echo "$PROXY_CA_CERT_B64" | base64 -d > /usr/local/share/ca-certificates/proxy-ca.crt && \
        update-ca-certificates; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends --option=Apt::Retries=3 upx-ucl



# Create a virtual environment for the app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# Upgrade pip using cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip

# Pre-install patchright and Chromium to cache this huge layer independently of the project's dependencies
# This runs BEFORE copying any project files so that UPX compression is permanently cached.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/ms-playwright \
    pip install patchright && \
    python -m patchright install chromium --no-shell && \
    rm -rf /ms-playwright/ffmpeg-* && \
    find /ms-playwright -name "*.pak*" | grep -vE "(resources|chrome_100|chrome_200|de|en-US|en-GB)\.pak" | xargs -r rm -f && \
    chrome_dir=$(ls -d /ms-playwright/chromium-* | grep -v headless_shell | head -n 1) && \
    chrome_inner_dir=$(ls -d "$chrome_dir"/chrome-* | head -n 1) && \
    arch=$(dpkg --print-architecture) && \
    if [ "$arch" = "amd64" ]; then \
        upx -9 /opt/venv/lib/python3.13/site-packages/patchright/driver/node; \
        upx -9 "$chrome_inner_dir/chrome"; \
    fi && \
    chmod -R a+rX /ms-playwright && \
    rm -rf /tmp/*

# Copy packaging metadata first to maximize caching
COPY pyproject.toml README.md LICENSE MANIFEST.in /build/

# Install dependencies (including optional dependencies like discord/sso)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .[all]

# Copy the application source code
COPY src/ /build/src/

# Install the application package into the virtual env (using cache)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .[all]

# Clean up python bytecodes and packaging tools in builder venv
RUN find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + && \
    pip uninstall -y pip setuptools wheel


# ==========================================
# Stage 2: Final minimal runner image
# ==========================================
FROM python:3.13-slim AS runner

WORKDIR /app

# Support proxy CA certificate and HTTP/HTTPS proxies if they are set in the environment
ARG PROXY_CA_CERT_B64
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Setup HTTPS sources for Debian and trust the proxy certificate if provided (with cache)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    if [ -n "$PROXY_CA_CERT_B64" ]; then \
        echo "Trusting custom proxy CA certificate..." && \
        echo "$PROXY_CA_CERT_B64" | base64 -d > /usr/local/share/ca-certificates/proxy-ca.crt && \
        update-ca-certificates; \
    fi

# Create unprivileged user
RUN adduser --disabled-password --gecos "" aniworld \
    && mkdir -p /app/Downloads /home/aniworld/.aniworld \
    && chown -R aniworld:aniworld /app /home/aniworld

# Install minimal system dependencies (xvfb and core Chromium shared libraries) (with cache)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends --option=Apt::Retries=3 \
    xvfb \
    ffmpeg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxext6

# Copy virtual env and playwright browsers from builder stage. ffmpeg is not in
# here, the runner installs it from apt above.
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /ms-playwright /ms-playwright

# Environments
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANIWORLD_DOWNLOAD_PATH=/app/Downloads \
    DISPLAY=:99 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# Ensure Downloads and configuration paths are writable by the unprivileged user
RUN chown -R aniworld:aniworld /app/Downloads /home/aniworld/.aniworld

USER aniworld

EXPOSE 8080

# This command will be inherited by the final stage
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & sleep 1 && exec aniworld --web-ui --web-expose --no-browser --web-port 8080"]


# ==========================================
# Stage 3: Squashed final runner
# ==========================================
FROM scratch AS final

# Copy the entire root filesystem from the runner stage to squash all layers
COPY --from=runner / /

# Redeclare all necessary metadata since scratch starts empty
ENV PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ANIWORLD_DOWNLOAD_PATH=/app/Downloads \
    DISPLAY=:99 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

USER aniworld

EXPOSE 8080

CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & sleep 1 && exec aniworld --web-ui --web-expose --no-browser --web-port 8080"]
