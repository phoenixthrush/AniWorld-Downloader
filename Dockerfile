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
    apt-get update && apt-get install -y --no-install-recommends upx-ucl

# Download static ffmpeg and ffprobe builds, extract and compress them with UPX (cached download)
RUN --mount=type=cache,target=/root/.cache/ffmpeg \
    TARGETARCH=${TARGETARCH} python -c "import urllib.request, zipfile, io, os, ssl, platform; ctx = ssl._create_unverified_context(); arch = os.environ.get('TARGETARCH'); arch = ('arm64' if ('arm64' in platform.machine().lower() or 'aarch64' in platform.machine().lower()) else 'amd64') if not arch else arch; suffix = 'linux-arm-64' if arch == 'arm64' else 'linux-64'; cache_dir = '/root/.cache/ffmpeg'; os.makedirs(cache_dir, exist_ok=True); f = lambda u, n, p: (open(p, 'wb').write(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla'}), context=ctx).read()) if not os.path.exists(p) else None, zipfile.ZipFile(p).extractall('/usr/local/bin'), os.chmod('/usr/local/bin/' + n, 0o755)); f(f'https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-{suffix}.zip', 'ffmpeg', os.path.join(cache_dir, f'ffmpeg-4.4.1-{suffix}.zip')); f(f'https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-{suffix}.zip', 'ffprobe', os.path.join(cache_dir, f'ffprobe-4.4.1-{suffix}.zip'))" && \
    upx -9 /usr/local/bin/ffmpeg && \
    upx -9 /usr/local/bin/ffprobe

# Create a virtual environment for the app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# Upgrade pip using cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip

# Copy packaging metadata first to maximize caching
COPY pyproject.toml README.md LICENSE MANIFEST.in /build/

# Install dependencies (including optional dependencies like discord/sso) and compress Node driver immediately
# This runs BEFORE COPY src/ so that UPX compression is fully cached when changing code files.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .[all] && \
    arch=$(dpkg --print-architecture) && \
    if [ "$arch" = "amd64" ]; then \
        upx -9 /opt/venv/lib/python3.13/site-packages/patchright/driver/node; \
    fi

# Pre-install patchright Chromium (using cache)
# Playwright/Patchright installs Chromium to /ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN --mount=type=cache,target=/root/.cache/ms-playwright \
    python -m patchright install chromium

# OPTIMIZATION: Clean up the Chromium installation to reduce image size
# Deleting headless shell entirely (saves ~180MB), locales other than de/en, and compressing the 266MB chrome binary using UPX (~170MB saved)
RUN rm -rf /ms-playwright/chromium_headless_shell-* && \
    rm -rf /ms-playwright/ffmpeg-* && \
    find /ms-playwright -name "*.pak*" | grep -vE "(resources|chrome_100|chrome_200|de|en-US|en-GB)\.pak" | xargs -r rm -f && \
    arch=$(dpkg --print-architecture) && \
    if [ "$arch" = "amd64" ]; then \
        upx -9 /ms-playwright/chromium-*/chrome-linux*/chrome; \
    fi && \
    rm -rf /root/.cache /tmp/*

# Copy the application source code
COPY src/ /build/src/

# Install the application package into the virtual env (using cache)
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .[all]

# Clean up python bytecodes in builder venv
RUN find /opt/venv -type d -name "__pycache__" -exec rm -rf {} +


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
    apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
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

# Copy virtual env, playwright browsers, and compressed static ffmpeg/ffprobe from builder stage
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /ms-playwright /ms-playwright
COPY --from=builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=builder /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# Grant read/execute access to browsers directory
RUN chmod -R a+rX /ms-playwright

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
CMD Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & sleep 1 && exec aniworld --web-ui --web-expose --no-browser --web-port 8080


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

CMD Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & sleep 1 && exec aniworld --web-ui --web-expose --no-browser --web-port 8080