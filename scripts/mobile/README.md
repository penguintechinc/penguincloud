# Mobile Build Scripts

## Overview

The mobile build scripts automate compilation and packaging of the Flutter-based mobile application for Android and iOS platforms. These scripts handle the complete build process, from dependency resolution to artifact generation, ensuring consistent builds across development and production environments.

**Supported Platforms:**
- **Android**: APK generation (debug and release variants)
- **iOS**: Build preparation (requires macOS with Xcode)

**Build Variants:**
- **Debug**: Unoptimized build with debugging symbols for development and testing
- **Release**: Optimized build with ProGuard/R8 obfuscation and minification for production
- **Profile**: Instrumented build for performance profiling and analysis

## Android Build

### Building Android APK

To build the Android application:

```bash
./scripts/mobile/build-android.sh
```

This script performs the following operations:
1. Resolves and downloads Flutter dependencies
2. Validates Android SDK configuration
3. Compiles Dart code to native Android code
4. Packages native libraries and assets
5. Signs the APK (debug builds use auto-generated key)
6. Generates both debug and release variants

### Output Location

Build artifacts are stored in:
```
services/mobile/build/app/outputs/flutter-apk/
```

### Build Artifacts

**app-debug.apk** (Typical size: 50-80 MB)
- Unoptimized debug build with full debugging symbols
- Auto-signed with debug keystore
- Suitable for testing on emulator or physical device
- Contains verbose logging output
- Slower startup time and higher memory usage

**app-release.apk** (Typical size: 30-50 MB)
- Production-ready optimized release build
- Code obfuscation and minification enabled
- Requires manual signing with release keystore for distribution
- Optimized for app store submission
- Smaller file size and faster startup

### Example Output

```
Flutter build complete!
Generated APK files:
  Debug:   services/mobile/build/app/outputs/flutter-apk/app-debug.apk (72 MB)
  Release: services/mobile/build/app/outputs/flutter-apk/app-release.apk (42 MB)

Build Information:
  Flutter Version:  3.16.0
  Build Timestamp:  2026-02-02 14:32:15 UTC
  Target Platform:  android-arm64
  Build Duration:   3m 47s
```

### Build Time Expectations

- **First build** (with dependency download): 5-10 minutes
- **Incremental build** (code changes only): 1-3 minutes
- **Release build** (with minification): 2-5 minutes
- Factors affecting build time:
  - Machine CPU cores and RAM availability
  - Network speed for dependency downloads
  - Size of code changes since last build
  - Whether ProGuard/R8 minification is enabled

## Building via Makefile

Build the Flutter mobile application using the provided Makefile:

```bash
make build-flutter
```

This target:
- Cleans previous build artifacts
- Runs the Android build script
- Validates build output
- Displays build results

### Smoke Tests

Verify the build and basic functionality:

```bash
make smoke-test-mobile
```

The smoke test includes:
- APK file existence and size validation
- Flutter SDK verification
- Android SDK configuration check
- Signing validation (debug certificate present)
- Runtime executable verification

## Build Output

### Information Displayed

The build output includes:
- **Build status**: Success/failure indication
- **APK paths**: Full file paths for generated artifacts
- **File sizes**: APK sizes for performance tracking
- **Build timestamps**: Exact build completion time
- **Version information**: Flutter, Android, and app versions
- **Build duration**: Total time for compilation and packaging

### Interpreting APK Sizes

- **Debug APK (50-80 MB)**: Typical for unoptimized builds with symbols
  - Larger size is acceptable for development
  - Indicates successful compilation and packaging
- **Release APK (30-50 MB)**: Expected after minification and optimization
  - Should be 30-50% smaller than debug APK
  - Suitable for Google Play Store submission

### Build Verification

After a successful build, verify:
1. **APK existence**: Both debug and release APKs present
2. **File integrity**: APKs have reasonable file sizes (>20 MB)
3. **Timestamps**: Current build date matches expected timeframe
4. **Version consistency**: Version number matches `.version` file

## Prerequisites

Before building, ensure your environment has:

### Required Software

- **Flutter SDK**: Version 3.16.0 or later
  - Install: https://flutter.dev/docs/get-started/install
  - Verify: `flutter --version`

- **Android SDK**: API level 34 (minimum 21)
  - Install via Android Studio or command-line tools
  - Verify: `flutter doctor`

- **Java Development Kit (JDK)**: Version 11 or 17
  - Required for Android compilation
  - Verify: `java -version`

### System Requirements

- **Disk space**: Minimum 2 GB free space for build artifacts
  - Flutter SDK: ~2 GB
  - Android SDK and NDK: ~5 GB
  - Build outputs: ~500 MB per build
- **RAM**: Minimum 4 GB (8 GB recommended)
- **Network**: Required for initial dependency download

### Environment Setup

Verify your setup with Flutter Doctor:

```bash
flutter doctor
```

Expected output shows:
- Flutter SDK path configured
- Android SDK path configured
- Connected devices or emulator available
- All required dependencies installed

## Troubleshooting

### Flutter Not Found

**Error**: `flutter: command not found`

**Solutions**:
1. Verify Flutter installation: `flutter --version`
2. Add Flutter to PATH: `export PATH="$PATH:~/flutter/bin"`
3. Check FLUTTER_HOME environment variable
4. Run `flutter doctor` to diagnose setup issues

### Android SDK Issues

**Error**: `Android SDK not found`

**Solutions**:
1. Install Android SDK: Download Android Studio
2. Set ANDROID_HOME: `export ANDROID_HOME=~/Android/Sdk`
3. Run `flutter doctor --android-licenses` to accept licenses
4. Verify with `flutter doctor -v`

### Java/JDK Errors

**Error**: `Java not found` or `Unsupported Java version`

**Solutions**:
1. Install JDK 11 or 17
2. Set JAVA_HOME: `export JAVA_HOME=/usr/libexec/java_home`
3. Verify: `java -version` (must show 11.x or 17.x)

### Build Cache Problems

**Error**: Build fails with cryptic errors or generates invalid APK

**Solutions**:
1. Clean build cache: `flutter clean`
2. Remove gradle cache: `rm -rf ~/.gradle/caches`
3. Rebuild from scratch: `./scripts/mobile/build-android.sh`
4. Check disk space: `df -h` (ensure >2 GB available)

### Out of Memory During Build

**Error**: `Java heap space` or build terminates unexpectedly

**Solutions**:
1. Increase Gradle heap: `export _JAVA_OPTIONS="-Xmx4g"`
2. Close other applications to free RAM
3. Use incremental builds instead of full rebuild
4. Check available memory: `free -h`

### Version Mismatch Errors

**Error**: Mismatched Flutter or Dart versions

**Solutions**:
1. Update Flutter: `flutter upgrade`
2. Verify version: `flutter --version`
3. Check pubspec.yaml for dependency constraints
4. Run `flutter pub get` to sync versions

## iOS Build (Future)

iOS builds require macOS with Xcode installed. iOS build script support is planned for future release.

**Requirements for iOS builds:**
- macOS 11.0 or later
- Xcode 13.0 or later
- iOS deployment target: iOS 12 or later
- Apple Developer account (for App Store submission)

**Future iOS build command:**
```bash
./scripts/mobile/build-ios.sh
```

Check back soon for full iOS build documentation and scripts.

---

**Last Updated**: 2026-02-02  
**Flutter Version**: 3.16.0+  
**Android SDK**: API 34 (minimum 21)  
**For issues or questions**: Refer to [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md) and [docs/TESTING.md](../../docs/TESTING.md)
