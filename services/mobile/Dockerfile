# Flutter CI Build Environment
# Debian bookworm base for Android builds (iOS requires macOS runner)
FROM debian:bookworm-slim@sha256:f06537653ac770703bc45b4b113475bd402f451e85223f0f2837acbf89ab020a AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl=7.88.1-10+deb12u15 \
    git=1:2.39.5-0+deb12u3 \
    unzip=6.0-28 \
    xz-utils=5.4.1-1+deb12u1 \
    zip=3.0-13 \
    libglu1-mesa=9.0.2-1.1 \
    openjdk-17-jdk-headless=17.0.20+8-1~deb12u1 \
    ca-certificates=20230311+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

# Set Java home
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"

# Install Flutter SDK
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="$FLUTTER_HOME/bin:$PATH"
ARG FLUTTER_VERSION=3.38.9
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
    | tar xJ -C /opt \
    && flutter config --no-analytics \
    && flutter precache --android

# Accept Android licenses
RUN yes | flutter doctor --android-licenses 2>/dev/null || true

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /opt/flutter

# Set working directory
WORKDIR /app
RUN chown -R appuser:appuser /app

USER appuser

# --- Dependencies stage ---
FROM base AS deps
COPY --chown=appuser:appuser pubspec.yaml pubspec.lock* ./
RUN flutter pub get

# --- Analysis stage ---
FROM deps AS analyze
COPY . .
RUN flutter analyze --no-fatal-infos

# --- Test stage ---
FROM analyze AS test
RUN flutter test

# --- Build stage ---
FROM test AS build
RUN flutter build apk --release && flutter build appbundle --release

# --- Output stage ---
FROM scratch AS output
COPY --from=build /app/build/app/outputs/flutter-apk/app-release.apk /app-release.apk
COPY --from=build /app/build/app/outputs/bundle/release/app-release.aab /app-release.aab
