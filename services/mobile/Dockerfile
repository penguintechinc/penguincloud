# Flutter CI Build Environment
# Debian bookworm base for Android builds (iOS requires macOS runner)
FROM debian:bookworm-slim@sha256:f06537653ac770703bc45b4b113475bd402f451e85223f0f2837acbf89ab020a AS base

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    unzip \
    xz-utils \
    zip \
    libglu1-mesa \
    openjdk-17-jdk-headless \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set Java home
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"

# Install Flutter SDK
ENV FLUTTER_HOME=/opt/flutter
ENV PATH="$FLUTTER_HOME/bin:$PATH"
ARG FLUTTER_VERSION=3.38.9
RUN curl -fsSL "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz" \
    | tar xJ -C /opt \
    && flutter config --no-analytics \
    && flutter precache --android

# Accept Android licenses
RUN yes | flutter doctor --android-licenses 2>/dev/null || true

# Set working directory
WORKDIR /app

# --- Dependencies stage ---
FROM base AS deps
COPY pubspec.yaml pubspec.lock* ./
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
RUN flutter build apk --release
RUN flutter build appbundle --release

# --- Output stage ---
FROM scratch AS output
COPY --from=build /app/build/app/outputs/flutter-apk/app-release.apk /app-release.apk
COPY --from=build /app/build/app/outputs/bundle/release/app-release.aab /app-release.aab
