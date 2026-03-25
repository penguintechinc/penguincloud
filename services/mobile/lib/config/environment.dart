import 'dart:io' show Platform;

class Environment {
  const Environment._();

  static const String appName = 'PenguinTech';
  static const String appVersion = '1.0.0';
  static const String appTagline = 'Enterprise Springboard';

  static String get apiBaseUrl {
    const envUrl = String.fromEnvironment('API_BASE_URL');
    if (envUrl.isNotEmpty) return envUrl;
    if (Platform.isAndroid) return 'http://10.0.2.2:5000';
    return 'http://localhost:5000';
  }

  static String get loginUrl => '$apiBaseUrl/api/v1/auth/login';
  static String get profileUrl => '$apiBaseUrl/api/v1/auth/profile';
  static String get refreshUrl => '$apiBaseUrl/api/v1/auth/refresh';

  static const String environment = String.fromEnvironment(
    'APP_ENV',
    defaultValue: 'development',
  );
}
