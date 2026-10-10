#!/bin/bash

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Build timestamp
BUILD_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
EPOCH_TIMESTAMP=$(date +%s)

# Verify we're in the right place
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MOBILE_APP_DIR="${PROJECT_ROOT}/services/mobile"

echo -e "${BLUE}=== Android Build Script ===${NC}"
echo -e "${BLUE}Build Time: ${BUILD_TIMESTAMP}${NC}"
echo ""

# Check if mobile app directory exists
if [ ! -d "${MOBILE_APP_DIR}" ]; then
  echo -e "${RED}Error: Mobile app directory not found at ${MOBILE_APP_DIR}${NC}"
  exit 1
fi

cd "${MOBILE_APP_DIR}"

# Check if pubspec.yaml exists
if [ ! -f "pubspec.yaml" ]; then
  echo -e "${RED}Error: pubspec.yaml not found in ${MOBILE_APP_DIR}${NC}"
  exit 1
fi

# Extract app version from pubspec.yaml
APP_VERSION=$(grep '^version:' pubspec.yaml | awk '{print $2}')
if [ -z "${APP_VERSION}" ]; then
  APP_VERSION="unknown"
fi

# Get Flutter version
FLUTTER_VERSION=$(flutter --version | head -n 1)

# Get Android SDK version from flutter doctor (best effort)
ANDROID_SDK_VERSION=$(flutter doctor -v 2>/dev/null | grep "Android SDK" | head -n 1 | sed 's/.*Android SDK at //' | sed 's/ .*//g' || echo "unknown")

echo -e "${YELLOW}Building Debug APK...${NC}"
if ! flutter build apk --debug; then
  echo -e "${RED}Error: Debug APK build failed${NC}"
  exit 1
fi

DEBUG_APK_PATH="${MOBILE_APP_DIR}/build/app/outputs/flutter-apk/app-debug.apk"

if [ ! -f "${DEBUG_APK_PATH}" ]; then
  echo -e "${RED}Error: Debug APK not found at expected path: ${DEBUG_APK_PATH}${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Debug APK built successfully${NC}"
echo ""

echo -e "${YELLOW}Building Release APK...${NC}"
if ! flutter build apk --release; then
  echo -e "${RED}Error: Release APK build failed${NC}"
  exit 1
fi

RELEASE_APK_PATH="${MOBILE_APP_DIR}/build/app/outputs/flutter-apk/app-release.apk"

if [ ! -f "${RELEASE_APK_PATH}" ]; then
  echo -e "${RED}Error: Release APK not found at expected path: ${RELEASE_APK_PATH}${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Release APK built successfully${NC}"
echo ""

# Get file sizes (handle both macOS and Linux)
if command -v stat &> /dev/null; then
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    DEBUG_SIZE_BYTES=$(stat -f%z "${DEBUG_APK_PATH}")
    RELEASE_SIZE_BYTES=$(stat -f%z "${RELEASE_APK_PATH}")
  else
    # Linux
    DEBUG_SIZE_BYTES=$(stat -c%s "${DEBUG_APK_PATH}")
    RELEASE_SIZE_BYTES=$(stat -c%s "${RELEASE_APK_PATH}")
  fi
else
  # Fallback using ls (less reliable but works)
  DEBUG_SIZE_BYTES=$(ls -l "${DEBUG_APK_PATH}" | awk '{print $5}')
  RELEASE_SIZE_BYTES=$(ls -l "${RELEASE_APK_PATH}" | awk '{print $5}')
fi

DEBUG_SIZE_MB=$(echo "scale=2; ${DEBUG_SIZE_BYTES} / 1024 / 1024" | bc)
RELEASE_SIZE_MB=$(echo "scale=2; ${RELEASE_SIZE_BYTES} / 1024 / 1024" | bc)

# Display build information
echo -e "${BLUE}=== Build Information ===${NC}"
echo -e "${BLUE}Build Timestamp:${NC} ${BUILD_TIMESTAMP} (epoch: ${EPOCH_TIMESTAMP})"
echo -e "${BLUE}App Version:${NC} ${APP_VERSION}"
echo -e "${BLUE}Flutter Version:${NC} ${FLUTTER_VERSION}"
echo -e "${BLUE}Android SDK:${NC} ${ANDROID_SDK_VERSION}"
echo ""

echo -e "${GREEN}=== APK Build Results ===${NC}"
echo -e "${GREEN}Debug APK:${NC}"
echo -e "  Path: ${DEBUG_APK_PATH}"
echo -e "  Size: ${DEBUG_SIZE_MB} MB"
echo ""
echo -e "${GREEN}Release APK:${NC}"
echo -e "  Path: ${RELEASE_APK_PATH}"
echo -e "  Size: ${RELEASE_SIZE_MB} MB"
echo ""

echo -e "${GREEN}✓ Android build completed successfully${NC}"
exit 0
