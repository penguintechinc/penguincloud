import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import 'providers/auth_provider.dart';
import 'screens/login_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/springboard_screen.dart';

class App extends StatelessWidget {
  const App({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'PenguinTech',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: ElderColors.slate950,
        appBarTheme: const AppBarTheme(
          backgroundColor: ElderColors.slate900,
          foregroundColor: ElderColors.amber400,
          elevation: 0,
        ),
        colorScheme: const ColorScheme.dark(
          primary: ElderColors.amber500,
          secondary: ElderColors.amber400,
          surface: ElderColors.slate800,
          error: ElderColors.red500,
        ),
        cardTheme: CardThemeData(
          color: ElderColors.slate800,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: const BorderSide(color: ElderColors.slate700),
          ),
        ),
        extensions: const [ElderThemeData.dark],
      ),
      routerConfig: _router(context),
    );
  }

  GoRouter _router(BuildContext context) {
    final authProvider = context.read<AuthProvider>();

    return GoRouter(
      initialLocation: '/home',
      redirect: (context, state) {
        final isAuthenticated = authProvider.isAuthenticated;
        final isLoginRoute = state.matchedLocation == '/login';

        if (!isAuthenticated && !isLoginRoute) return '/login';
        if (isAuthenticated && isLoginRoute) return '/home';
        return null;
      },
      refreshListenable: authProvider,
      routes: [
        GoRoute(
          path: '/login',
          builder: (context, state) => const LoginScreen(),
        ),
        StatefulShellRoute.indexedStack(
          builder: (context, state, navigationShell) {
            return SpringboardScreen(navigationShell: navigationShell);
          },
          branches: [
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/home',
                  builder: (context, state) => const SpringboardHomePage(),
                ),
              ],
            ),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/apps',
                  builder: (context, state) => const SpringboardGrid(),
                ),
              ],
            ),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: '/profile',
                  builder: (context, state) => const ProfileScreen(),
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}
