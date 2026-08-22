import 'package:dio/dio.dart';

import '../config/environment.dart';
import 'secure_storage.dart';

class ApiClient {
  ApiClient({required this.secureStorage, Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: Environment.apiBaseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
              headers: {'Content-Type': 'application/json'},
            ),
          ) {
    _dio.interceptors.add(_authInterceptor());
  }

  final Dio _dio;
  final SecureStorage secureStorage;
  VoidCallback? onUnauthorized;

  Dio get dio => _dio;

  Interceptor _authInterceptor() => InterceptorsWrapper(
    onRequest: (options, handler) async {
      final token = await secureStorage.getToken();
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
      handler.next(options);
    },
    onError: (error, handler) async {
      if (error.response?.statusCode == 401) {
        await secureStorage.clearAll();
        onUnauthorized?.call();
      }
      handler.next(error);
    },
  );
}

typedef VoidCallback = void Function();
