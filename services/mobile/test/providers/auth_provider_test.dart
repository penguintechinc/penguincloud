import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/providers/auth_provider.dart';
import 'package:mobile/services/api_client.dart';
import 'package:mobile/services/secure_storage.dart';

class MockSecureStorage extends Mock implements SecureStorage {}

class MockDio extends Mock implements Dio {}

class MockApiClient extends Mock implements ApiClient {
  @override
  set onUnauthorized(void Function()? callback) {}
}

void main() {
  late MockSecureStorage mockStorage;
  late MockApiClient mockApiClient;
  late MockDio mockDio;
  late AuthProvider authProvider;

  setUp(() {
    mockStorage = MockSecureStorage();
    mockApiClient = MockApiClient();
    mockDio = MockDio();
    when(() => mockApiClient.secureStorage).thenReturn(mockStorage);
    when(() => mockApiClient.dio).thenReturn(mockDio);
    authProvider = AuthProvider(
      secureStorage: mockStorage,
      apiClient: mockApiClient,
    );
  });

  group('AuthProvider', () {
    test('initial state is not authenticated', () {
      expect(authProvider.isAuthenticated, isFalse);
      expect(authProvider.currentUser, isNull);
      expect(authProvider.isLoading, isFalse);
    });

    test('initialize loads user from storage', () async {
      when(() => mockStorage.getUserData()).thenAnswer((_) async => {
            'id': 'user-1',
            'email': 'test@example.com',
            'name': 'Test',
            'roles': ['viewer'],
          });

      await authProvider.initialize();

      expect(authProvider.isAuthenticated, isTrue);
      expect(authProvider.currentUser!.email, 'test@example.com');
    });

    test('initialize handles no stored user', () async {
      when(() => mockStorage.getUserData()).thenAnswer((_) async => null);

      await authProvider.initialize();

      expect(authProvider.isAuthenticated, isFalse);
    });

    test('logout clears current user', () async {
      // Setup: first initialize with a user
      when(() => mockStorage.getUserData()).thenAnswer((_) async => {
            'id': 'user-1',
            'email': 'test@example.com',
            'roles': [],
          });
      await authProvider.initialize();
      expect(authProvider.isAuthenticated, isTrue);

      // Mock Dio.post to throw DioException (server unreachable)
      when(() => mockDio.post(any())).thenThrow(
        DioException(requestOptions: RequestOptions()),
      );
      when(() => mockStorage.clearAll()).thenAnswer((_) async {});

      await authProvider.logout();

      expect(authProvider.isAuthenticated, isFalse);
      expect(authProvider.currentUser, isNull);
    });
  });
}
