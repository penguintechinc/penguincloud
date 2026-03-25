import 'package:flutter/foundation.dart';
import 'package:flutter_libs/flutter_libs.dart';

import '../models/user.dart';
import '../services/api_client.dart';
import '../services/auth_service.dart';
import '../services/secure_storage.dart';

class AuthProvider extends ChangeNotifier {
  AuthProvider({
    required SecureStorage secureStorage,
    required ApiClient apiClient,
  })  : _secureStorage = secureStorage,
        _apiClient = apiClient,
        _authService = AuthService(
          apiClient: apiClient,
          secureStorage: secureStorage,
        ) {
    _apiClient.onUnauthorized = _handleUnauthorized;
  }

  final SecureStorage _secureStorage;
  final ApiClient _apiClient;
  final AuthService _authService;

  User? _currentUser;
  bool _isLoading = false;
  String? _error;

  User? get currentUser => _currentUser;
  bool get isAuthenticated => _currentUser != null;
  bool get isLoading => _isLoading;
  String? get error => _error;

  AuthService get authService => _authService;

  Future<void> initialize() async {
    _isLoading = true;
    notifyListeners();
    try {
      _currentUser = await _authService.getCurrentUser();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> login(String email, String password) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      _currentUser = await _authService.login(email, password);
      return _currentUser != null;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> handleLoginSuccess(LoginResponse response) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      await _authService.handleLoginResponse(response);
      if (response.user != null) {
        _currentUser = User(
          id: response.user!.id,
          email: response.user!.email,
          name: response.user!.name,
          roles: response.user!.roles,
        );
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _isLoading = true;
    notifyListeners();
    try {
      await _authService.logout();
      _currentUser = null;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void _handleUnauthorized() {
    _currentUser = null;
    _secureStorage.clearAll();
    notifyListeners();
  }

  Future<void> refreshProfile() async {
    try {
      _currentUser = await _authService.fetchProfile();
      notifyListeners();
    } catch (_) {
      // Silently fail — keep existing user data.
    }
  }
}
