# Flutter/Dart Shared Library — `flutter_libs`

> **Status**: Alpha (v0.1.0) — available in the `penguin-libs` monorepo at `packages/flutter_libs/`.

## Package

**Name**: `flutter_libs` (Dart package)
**Location**: `~/code/penguin-libs/packages/flutter_libs/`
**Install**:

```yaml
# pubspec.yaml
dependencies:
  flutter_libs:
    git:
      url: https://github.com/penguintechinc/penguin-libs.git
      path: packages/flutter_libs
      ref: main
```

## Features

The Flutter package mirrors patterns used by the Python, Go, and React packages:

### Sanitized Logging

Matching the `SanitizedLogger` from Python and Go — same sensitive keys, same email masking:

```dart
final log = SanitizedLogger('AuthService');

log.info('Login attempt', {
  'email': 'user@example.com',    // masked to [email]@example.com
  'password': 'secret',           // redacted
  'remember_me': true,            // passed through
});
```

### Console Version Logging

Matching `AppConsoleVersion` from the React package:

```dart
PenguinConsoleVersion.log(
  appName: 'My Mobile App',
  version: '1.2.3',
  buildEpoch: 1737720000,
  environment: 'development',
  metadata: {
    'API URL': 'http://localhost:5000',
    'Platform': Platform.operatingSystem,
  },
);
```

### API Client

Pre-configured HTTP client with JWT auth, matching the web `apiClient` interceptor pattern:

```dart
final api = PenguinApiClient(baseUrl: 'http://localhost:5000');

final response = await api.get('/api/v1/users');
await api.post('/api/v1/users', data: {'name': 'Jane', 'email': 'jane@example.com'});
// JWT token auto-attached, 401 triggers logout
```

### Auth Service

Login, logout, biometric unlock, secure token storage (Keychain on iOS, EncryptedSharedPreferences on Android):

```dart
final auth = PenguinAuthService(apiClient: api);
await auth.login(email: 'user@example.com', password: 'secret');
if (await auth.isBiometricAvailable()) {
  await auth.authenticateWithBiometrics(reason: 'Unlock app');
}
```

### Theme

Penguin Tech dark/gold palette as `ThemeData`:

```dart
MaterialApp(
  darkTheme: PenguinTheme.dark,
  theme: PenguinTheme.light,
  themeMode: ThemeMode.dark,
);
```

### Adaptive Layout

Phone vs tablet switching:

```dart
AdaptiveLayout(
  phone: PhoneHomeLayout(),
  tablet: TabletHomeLayout(),
);
```

### Validation

PyDAL-style chainable validators consistent with Python and Go:

```dart
final validator = chain([
  IsNotEmpty(),
  IsLength(min: 3, max: 255),
  IsEmail(),
]);

TextFormField(
  validator: (value) => validator.validate(value ?? '').errorOrNull,
);
```

## Contributing

When working on this package:

1. The package lives at `packages/flutter_libs/` in the `penguin-libs` monorepo
2. Follow the same redaction rules as Python/Go for sanitized logging
3. Uses `http` for HTTP, `shared_preferences` for local storage
4. Export everything from a single barrel file
5. Add tests and update this document with final API changes

## Related

- [Shared Libraries Overview](./overview.md)
- [Mobile Standards](../standards/MOBILE.md)
- [Claude Mobile Rules](../../.claude/mobile.md)
