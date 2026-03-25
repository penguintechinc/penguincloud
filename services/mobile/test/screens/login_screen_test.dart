import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:provider/provider.dart';
import 'package:mobile/providers/auth_provider.dart';
import 'package:mobile/screens/login_screen.dart';
import 'package:mobile/services/api_client.dart';
import 'package:mobile/services/secure_storage.dart';

class MockSecureStorage extends Mock implements SecureStorage {}

class MockApiClient extends Mock implements ApiClient {
  @override
  set onUnauthorized(void Function()? callback) {}
}

void main() {
  late MockSecureStorage mockStorage;
  late MockApiClient mockApiClient;

  setUp(() {
    mockStorage = MockSecureStorage();
    mockApiClient = MockApiClient();
    when(() => mockApiClient.secureStorage).thenReturn(mockStorage);
    when(() => mockStorage.getUserData()).thenAnswer((_) async => null);
  });

  Widget buildTestWidget() {
    return ChangeNotifierProvider(
      create: (_) => AuthProvider(
        secureStorage: mockStorage,
        apiClient: mockApiClient,
      ),
      child: MaterialApp(
        theme: ThemeData.dark().copyWith(
          extensions: const [ElderThemeData.dark],
        ),
        home: const LoginScreen(),
      ),
    );
  }

  group('LoginScreen', () {
    testWidgets('renders LoginPageBuilder on phone layout', (tester) async {
      tester.view.physicalSize = const Size(400, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.byType(LoginPageBuilder), findsOneWidget);
    });

    testWidgets('renders branding pane on tablet layout', (tester) async {
      tester.view.physicalSize = const Size(1024, 768);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildTestWidget());
      await tester.pumpAndSettle();

      expect(find.text('PenguinTech'), findsWidgets);
      expect(find.byType(LoginPageBuilder), findsOneWidget);
    });
  });
}
