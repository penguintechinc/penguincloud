import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'config/environment.dart';
import 'providers/auth_provider.dart';
import 'services/api_client.dart';
import 'services/secure_storage.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  final secureStorage = SecureStorage();
  final apiClient = ApiClient(secureStorage: secureStorage);

  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthProvider(
        secureStorage: secureStorage,
        apiClient: apiClient,
      )..initialize(),
      child: const _AppWithVersionLogging(),
    ),
  );
}

class _AppWithVersionLogging extends StatelessWidget {
  const _AppWithVersionLogging();

  @override
  Widget build(BuildContext context) {
    return const Stack(
      children: [
        App(),
        ConsoleVersion(
          appName: Environment.appName,
          version: Environment.appVersion,
          environment: Environment.environment,
        ),
      ],
    );
  }
}
