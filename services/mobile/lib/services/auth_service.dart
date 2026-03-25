import 'package:dio/dio.dart';
import 'package:flutter_libs/flutter_libs.dart';

import '../config/environment.dart';
import '../models/user.dart';
import 'api_client.dart';
import 'secure_storage.dart';

class AuthService {
  AuthService({
    required this.apiClient,
    required this.secureStorage,
  });

  final ApiClient apiClient;
  final SecureStorage secureStorage;

  Future<User?> login(String email, String password) async {
    final response = await apiClient.dio.post(
      Environment.loginUrl,
      data: {'email': email, 'password': password},
    );
    final data = response.data as Map<String, dynamic>;
    if (data['token'] != null) {
      await secureStorage.saveToken(data['token'] as String);
    }
    if (data['refreshToken'] != null) {
      await secureStorage.saveRefreshToken(data['refreshToken'] as String);
    }
    if (data['user'] != null) {
      final userData = data['user'] as Map<String, dynamic>;
      await secureStorage.saveUserData(userData);
      return User.fromJson(userData);
    }
    return null;
  }

  Future<void> handleLoginResponse(LoginResponse response) async {
    if (!response.success) return;
    if (response.token != null) {
      await secureStorage.saveToken(response.token!);
    }
    if (response.refreshToken != null) {
      await secureStorage.saveRefreshToken(response.refreshToken!);
    }
    if (response.user != null) {
      await secureStorage.saveUserData({
        'id': response.user!.id,
        'email': response.user!.email,
        'name': response.user!.name,
        'roles': response.user!.roles,
      });
    }
  }

  Future<void> logout() async {
    try {
      await apiClient.dio.post('${Environment.apiBaseUrl}/api/v1/auth/logout');
    } on DioException {
      // Ignore logout API errors — clear local state regardless.
    }
    await secureStorage.clearAll();
  }

  Future<User?> getCurrentUser() async {
    final userData = await secureStorage.getUserData();
    if (userData == null) return null;
    return User.fromJson(userData);
  }

  Future<bool> isAuthenticated() async {
    final token = await secureStorage.getToken();
    return token != null;
  }

  Future<User?> fetchProfile() async {
    final response = await apiClient.dio.get(Environment.profileUrl);
    final data = response.data as Map<String, dynamic>;
    if (data['user'] != null) {
      final userData = data['user'] as Map<String, dynamic>;
      await secureStorage.saveUserData(userData);
      return User.fromJson(userData);
    }
    return null;
  }
}
