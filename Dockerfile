FROM python:3.13-alpine

WORKDIR /app

# Install ffmpeg for runtime media operations (e.g., muxing/transcoding helpers)
RUN apk add --no-cache ffmpeg

# Create an unprivileged user and pre-create the app/runtime directories it needs
# This avoids running the app as root and prevents permission issues at runtime
RUN adduser -D -h /home/aniworld aniworld \
    && mkdir -p /app/Downloads /home/aniworld/.aniworld \
    && chown -R aniworld:aniworld /app /home/aniworld

# Container-friendly Python defaults:
# - Disable .pyc bytecode writes (keeps layers/volumes cleaner)
# - Unbuffer stdout/stderr so logs appear immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Default download directory used by the application
ENV ANIWORLD_DOWNLOAD_PATH=/app/Downloads

# Default sync directory used by the application
ENV ANIWORLD_SYNC_PATH=/app/Sync

# Copy packaging metadata first to maximize Docker layer cache hits for dependency installs
COPY pyproject.toml /app/
COPY README.md LICENSE MANIFEST.in /app/

# Keep pip current
RUN pip install --no-cache-dir --upgrade pip

# Copy the application source code
COPY src/ /app/src/

# Install the project into the image
RUN pip install --no-cache-dir .

# Ensure the runtime directories are still writable after COPY overwrote ownership
RUN chown -R aniworld:aniworld /app/Downloads /home/aniworld/.aniworld

# Drop privileges for runtime
USER aniworld

# Expose the web UI port
EXPOSE 8080

# Run the web UI, exposed on all interfaces with no browser
CMD ["aniworld", "--web-ui", "--web-expose", "--no-browser", "--web-port", "8080"]