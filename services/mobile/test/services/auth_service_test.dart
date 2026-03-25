import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:mobile/services/api_client.dart';
import 'package:mobile/services/auth_service.dart';
import 'package:mobile/services/secure_storage.dart';

class MockDio extends Mock implements Dio {}

class MockSecureStorage extends Mock implements SecureStorage {}

class MockApiClient extends Mock implements ApiClient {}

void main() {
  late MockDio mockDio;
  late MockSecureStorage mockStorage;
  late MockApiClient mockApiClient;
  late AuthService authService;

  setUp(() {
    mockDio = MockDio();
    mockStorage = MockSecureStorage();
    mockApiClient = MockApiClient();
    when(() => mockApiClient.dio).thenReturn(mockDio);
    when(() => mockApiClient.secureStorage).thenReturn(mockStorage);
    authService = AuthService(
      apiClient: mockApiClient,
      secureStorage: mockStorage,
    );
  });

  group('AuthService', () {
    group('login', () {
      test('stores token and returns user on success', () async {
        when(() => mockDio.post(
              any(),
              data: any(named: 'data'),
            )).thenAnswer((_) async => Response(
              requestOptions: RequestOptions(),
              statusCode: 200,
              data: {
                'token': 'test-token',
                'refreshToken': 'test-refresh',
                'user': {
                  'id': 'user-1',
                  'email': 'test@example.com',
                  'name': 'Test User',
                  'roles': ['admin'],
                },
              },
            ));
        when(() => mockStorage.saveToken(any())).thenAnswer((_) async {});
        when(() => mockStorage.saveRefreshToken(any()))
            .thenAnswer((_) async {});
        when(() => mockStorage.saveUserData(any())).thenAnswer((_) async {});

        final user = await authService.login('test@example.com', 'password');

        expect(user, isNotNull);
        expect(user!.email, 'test@example.com');
        expect(user.id, 'user-1');
        expect(user.roles, contains('admin'));
        verify(() => mockStorage.saveToken('test-token')).called(1);
        verify(() => mockStorage.saveRefreshToken('test-refresh')).called(1);
      });

      test('returns null when no user in response', () async {
        when(() => mockDio.post(
              any(),
              data: any(named: 'data'),
            )).thenAnswer((_) async => Response(
              requestOptions: RequestOptions(),
              statusCode: 200,
              data: {'token': 'test-token'},
            ));
        when(() => mockStorage.saveToken(any())).thenAnswer((_) async {});

        final user = await authService.login('test@example.com', 'password');

        expect(user, isNull);
      });
    });

    group('logout', () {
      test('clears storage', () async {
        when(() => mockDio.post(any())).thenAnswer((_) async => Response(
              requestOptions: RequestOptions(),
              statusCode: 200,
            ));
        when(() => mockStorage.clearAll()).thenAnswer((_) async {});

        await authService.logout();

        verify(() => mockStorage.clearAll()).called(1);
      });

      test('clears storage even on API error', () async {
        when(() => mockDio.post(any())).thenThrow(
          DioException(requestOptions: RequestOptions()),
        );
        when(() => mockStorage.clearAll()).thenAnswer((_) async {});

        await authService.logout();

        verify(() => mockStorage.clearAll()).called(1);
      });
    });

    group('isAuthenticated', () {
      test('returns true when token exists', () async {
        when(() => mockStorage.getToken())
            .thenAnswer((_) async => 'some-token');

        final result = await authService.isAuthenticated();

        expect(result, isTrue);
      });

      test('returns false when token is null', () async {
        when(() => mockStorage.getToken()).thenAnswer((_) async => null);

        final result = await authService.isAuthenticated();

        expect(result, isFalse);
      });
    });

    group('getCurrentUser', () {
      test('returns user from storage', () async {
        when(() => mockStorage.getUserData()).thenAnswer((_) async => {
              'id': 'user-1',
              'email': 'test@example.com',
              'name': 'Test User',
              'roles': ['admin'],
            });

        final user = await authService.getCurrentUser();

        expect(user, isNotNull);
        expect(user!.email, 'test@example.com');
      });

      test('returns null when no stored data', () async {
        when(() => mockStorage.getUserData()).thenAnswer((_) async => null);

        final user = await authService.getCurrentUser();

        expect(user, isNull);
      });
    });
  });
}
