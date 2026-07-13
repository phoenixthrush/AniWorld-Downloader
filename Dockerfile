FROM python:3.13-slim

WORKDIR /app

RUN mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

# Install ffmpeg, Xvfb and system dependencies required by Chromium (patchright)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
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
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# Create an unprivileged user and pre-create the app/runtime directories it needs
# This avoids running the app as root and prevents permission issues at runtime
RUN adduser --disabled-password --gecos "" aniworld \
    && mkdir -p /app/Downloads /home/aniworld/.aniworld \
    && chown -R aniworld:aniworld /app /home/aniworld

# Container-friendly Python defaults:
# - Disable .pyc bytecode writes (keeps layers/volumes cleaner)
# - Unbuffer stdout/stderr so logs appear immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Default download directory used by the application
ENV ANIWORLD_DOWNLOAD_PATH=/app/Downloads

# Virtual display for headless Chromium (patchright) — headed mode works via Xvfb
ENV DISPLAY=:99

# Install the patchright browser into a shared, world-readable location instead
# of a per-user cache. The browser install runs as root but the app runs as the
# unprivileged "aniworld" user, so without this the runtime can't find Chromium
# (it looks in /home/aniworld/.cache and the root install went to /root/.cache).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copy packaging metadata first to maximize Docker layer cache hits for dependency installs
COPY pyproject.toml /app/
COPY README.md LICENSE MANIFEST.in /app/

# Keep pip current
RUN pip install --no-cache-dir --upgrade pip

# Copy the application source code
COPY src/ /app/src/

# Install the project into the image
RUN pip install --no-cache-dir .

# Pre-install patchright Chromium into the image so it's available at runtime.
# Installs into PLAYWRIGHT_BROWSERS_PATH (/ms-playwright) and makes it readable
# by every user so the unprivileged runtime user can launch it.
RUN python -m patchright install chromium \
    && chmod -R a+rX /ms-playwright

# Ensure the runtime directories are still writable after COPY overwrote ownership
RUN chown -R aniworld:aniworld /app/Downloads /home/aniworld/.aniworld

# Drop privileges for runtime
USER aniworld

# Expose the web UI port
EXPOSE 8080

# Start Xvfb virtual display on :99, then launch the web UI
CMD Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & sleep 1 && exec aniworld --web-ui --web-expose --no-browser --web-port 8080