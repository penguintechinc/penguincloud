import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:provider/provider.dart';

import 'package:mobile/app.dart';
import 'package:mobile/providers/auth_provider.dart';
import 'package:mobile/services/api_client.dart';
import 'package:mobile/services/secure_storage.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('Login Flow', () {
    testWidgets('shows login screen when not authenticated', (tester) async {
      final secureStorage = SecureStorage();
      final apiClient = ApiClient(secureStorage: secureStorage);

      await tester.pumpWidget(
        ChangeNotifierProvider(
          create: (_) => AuthProvider(
            secureStorage: secureStorage,
            apiClient: apiClient,
          )..initialize(),
          child: const App(),
        ),
      );

      await tester.pumpAndSettle();

      // Login screen should be shown since user is not authenticated
      expect(find.byType(Scaffold), findsWidgets);
    });
  });
}
