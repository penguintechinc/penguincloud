import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:provider/provider.dart';

import '../config/environment.dart';
import '../providers/auth_provider.dart';
import '../widgets/adaptive_layout.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AdaptiveLayout(
        phoneLayout: _PhoneLoginLayout(),
        tabletLayout: _TabletLoginLayout(),
      ),
    );
  }
}

class _PhoneLoginLayout extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: _buildLoginBuilder(context),
      ),
    );
  }
}

class _TabletLoginLayout extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final elder = Theme.of(context).extension<ElderThemeData>();
    return Row(
      children: [
        Expanded(
          child: Container(
            color: elder?.cardBackground ?? const Color(0xFF1E293B),
            child: Center(
              child: Padding(
                padding: const EdgeInsets.all(48),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.rocket_launch,
                      size: 80,
                      color: elder?.titleText ?? const Color(0xFFFBBF24),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      Environment.appName,
                      style: TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                        color: elder?.titleText ?? const Color(0xFFFBBF24),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      Environment.appTagline,
                      style: TextStyle(
                        fontSize: 16,
                        color: elder?.subtitleText ?? const Color(0xFF94A3B8),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        Expanded(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(48),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 400),
                child: _buildLoginBuilder(context),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

Widget _buildLoginBuilder(BuildContext context) {
  final authProvider = context.read<AuthProvider>();
  return LoginPageBuilder(
    apiConfig: LoginApiConfig(loginUrl: Environment.loginUrl),
    branding: const BrandingConfig(
      appName: Environment.appName,
      logo: Icon(Icons.rocket_launch, size: 48, color: Color(0xFFFBBF24)),
      tagline: Environment.appTagline,
    ),
    mfaConfig: const MFAConfig(enabled: true),
    onLoginSuccess: (response) {
      authProvider.handleLoginSuccess(response);
    },
    onLoginError: (error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error),
          backgroundColor: const Color(0xFFEF4444),
        ),
      );
    },
  );
}
