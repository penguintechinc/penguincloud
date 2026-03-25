#!/bin/bash

set -e

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Android Mobile App Build Smoke Test ===${NC}"

# Test 1: Verify Flutter is installed
echo -e "\n${BLUE}[1/7]${NC} Checking Flutter installation..."
if ! flutter --version > /dev/null 2>&1; then
    echo -e "${RED}❌ Flutter is not installed or not in PATH${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Flutter installed${NC}"

# Test 2: Change to mobile service directory
echo -e "\n${BLUE}[2/7]${NC} Navigating to services/mobile directory..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../" && pwd)"
MOBILE_DIR="${PROJECT_ROOT}/services/mobile"

if [ ! -d "$MOBILE_DIR" ]; then
    echo -e "${RED}❌ Mobile service directory not found at ${MOBILE_DIR}${NC}"
    exit 1
fi
cd "$MOBILE_DIR"
echo -e "${GREEN}✅ In mobile directory: ${MOBILE_DIR}${NC}"

# Test 3: Run flutter pub get
echo -e "\n${BLUE}[3/7]${NC} Running flutter pub get..."
if ! flutter pub get > /tmp/flutter_pub_get.log 2>&1; then
    echo -e "${RED}❌ flutter pub get failed${NC}"
    cat /tmp/flutter_pub_get.log
    exit 1
fi
echo -e "${GREEN}✅ Dependencies resolved${NC}"

# Test 4: Run flutter analyze
echo -e "\n${BLUE}[4/7]${NC} Running flutter analyze..."
if ! flutter analyze --no-fatal-infos > /tmp/flutter_analyze.log 2>&1; then
    echo -e "${RED}❌ flutter analyze failed${NC}"
    cat /tmp/flutter_analyze.log
    exit 1
fi
echo -e "${GREEN}✅ Analysis passed${NC}"

# Test 5: Execute Android build script
echo -e "\n${BLUE}[5/7]${NC} Executing Android build script..."
BUILD_SCRIPT="${PROJECT_ROOT}/scripts/mobile/build-android.sh"
if [ ! -f "$BUILD_SCRIPT" ]; then
    echo -e "${RED}❌ Build script not found at ${BUILD_SCRIPT}${NC}"
    exit 1
fi

if ! bash "$BUILD_SCRIPT" > /tmp/android_build.log 2>&1; then
    echo -e "${RED}❌ Android build failed${NC}"
    tail -50 /tmp/android_build.log
    exit 1
fi
echo -e "${GREEN}✅ Android build completed${NC}"

# Test 6: Verify APK artifact exists
echo -e "\n${BLUE}[6/7]${NC} Verifying APK artifact..."
APK_PATH="${MOBILE_DIR}/build/app/outputs/flutter-apk/app-release.apk"
if [ ! -f "$APK_PATH" ]; then
    echo -e "${RED}❌ APK not found at ${APK_PATH}${NC}"
    exit 1
fi
echo -e "${GREEN}✅ APK artifact exists${NC}"

# Test 7: Verify APK file size (at least 5MB)
echo -e "\n${BLUE}[7/7]${NC} Verifying APK file size..."
# Handle both Linux and macOS stat syntax
if [[ "$OSTYPE" == "darwin"* ]]; then
    APK_SIZE=$(stat -f%z "$APK_PATH")
else
    APK_SIZE=$(stat -c%s "$APK_PATH")
fi

MIN_SIZE=$((5 * 1024 * 1024))  # 5MB in bytes

if [ "$APK_SIZE" -lt "$MIN_SIZE" ]; then
    echo -e "${RED}❌ APK file size ($(numfmt --to=iec-i --suffix=B $APK_SIZE 2>/dev/null || echo "$APK_SIZE bytes")) is less than 5MB${NC}"
    exit 1
fi

# Convert bytes to MB for display
APK_SIZE_MB=$((APK_SIZE / 1024 / 1024))
echo -e "${GREEN}✅ APK file size is valid (${APK_SIZE_MB}MB)${NC}"

echo -e "\n${GREEN}=== All Android Build Smoke Tests Passed ===${NC}"
exit 0
