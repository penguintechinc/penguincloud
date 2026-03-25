import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../utils/constants.dart';
import '../widgets/adaptive_layout.dart';
import '../widgets/springboard_tile.dart';

class SpringboardScreen extends StatelessWidget {
  const SpringboardScreen({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    return AdaptiveLayout(
      phoneLayout: _PhoneSpringboard(navigationShell: navigationShell),
      tabletLayout: _TabletSpringboard(navigationShell: navigationShell),
    );
  }
}

class _PhoneSpringboard extends StatelessWidget {
  const _PhoneSpringboard({required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: navigationShell.currentIndex,
        onTap: (index) => navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        ),
        selectedItemColor: const Color(0xFFFBBF24),
        unselectedItemColor: const Color(0xFF94A3B8),
        backgroundColor: const Color(0xFF1E293B),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: 'Home',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.apps),
            label: 'Apps',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.person),
            label: 'Profile',
          ),
        ],
      ),
    );
  }
}

class _TabletSpringboard extends StatelessWidget {
  const _TabletSpringboard({required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final authProvider = context.watch<AuthProvider>();
    final userRole = authProvider.currentUser?.roles.isNotEmpty == true
        ? authProvider.currentUser!.roles.first
        : null;

    return Scaffold(
      body: Row(
        children: [
          SidebarMenu(
            activePath: _currentPath(navigationShell.currentIndex),
            userRole: userRole,
            logo: const Padding(
              padding: EdgeInsets.all(16),
              child: Row(
                children: [
                  Icon(Icons.rocket_launch, color: Color(0xFFFBBF24)),
                  SizedBox(width: 8),
                  Text(
                    'PenguinTech',
                    style: TextStyle(
                      color: Color(0xFFFBBF24),
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                ],
              ),
            ),
            onItemTap: (item) {
              final index = _indexForPath(item.href);
              if (index >= 0) {
                navigationShell.goBranch(
                  index,
                  initialLocation: index == navigationShell.currentIndex,
                );
              }
            },
            categories: const [
              MenuCategory(
                header: 'Navigation',
                items: [
                  MenuItem(
                    name: 'Home',
                    href: '/home',
                    icon: Icons.home,
                  ),
                  MenuItem(
                    name: 'Apps',
                    href: '/apps',
                    icon: Icons.apps,
                  ),
                  MenuItem(
                    name: 'Profile',
                    href: '/profile',
                    icon: Icons.person,
                  ),
                ],
              ),
            ],
          ),
          Expanded(child: navigationShell),
        ],
      ),
    );
  }

  String _currentPath(int index) {
    switch (index) {
      case 0:
        return '/home';
      case 1:
        return '/apps';
      case 2:
        return '/profile';
      default:
        return '/home';
    }
  }

  int _indexForPath(String path) {
    switch (path) {
      case '/home':
        return 0;
      case '/apps':
        return 1;
      case '/profile':
        return 2;
      default:
        return -1;
    }
  }
}

class SpringboardGrid extends StatelessWidget {
  const SpringboardGrid({super.key});

  @override
  Widget build(BuildContext context) {
    final authProvider = context.watch<AuthProvider>();
    final userRoles = authProvider.currentUser?.roles ?? [];
    final items = AppConstants.defaultItems
        .where((item) => item.isVisibleTo(userRoles))
        .toList();

    return LayoutBuilder(
      builder: (context, constraints) {
        final crossAxisCount =
            constraints.maxWidth >= AppConstants.tabletLandscapeBreakpoint
                ? AppConstants.tabletLandscapeGridColumns
                : constraints.maxWidth >= AppConstants.phoneBreakpoint
                    ? AppConstants.tabletGridColumns
                    : AppConstants.phoneGridColumns;

        return GridView.builder(
          padding: const EdgeInsets.all(AppConstants.gridSpacing),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: crossAxisCount,
            crossAxisSpacing: AppConstants.gridSpacing,
            mainAxisSpacing: AppConstants.gridSpacing,
            childAspectRatio: AppConstants.tileAspectRatio,
          ),
          itemCount: items.length,
          itemBuilder: (context, index) {
            return SpringboardTile(
              item: items[index],
              onTap: () {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('Navigate to ${items[index].title}'),
                    duration: const Duration(seconds: 1),
                  ),
                );
              },
            );
          },
        );
      },
    );
  }
}

class SpringboardHomePage extends StatelessWidget {
  const SpringboardHomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final elder = Theme.of(context).extension<ElderThemeData>();
    final authProvider = context.watch<AuthProvider>();
    final userName = authProvider.currentUser?.name ??
        authProvider.currentUser?.email ??
        'User';

    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
            child: Text(
              'Welcome, $userName',
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: elder?.titleText ?? const Color(0xFFFBBF24),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 16),
            child: Text(
              'Your springboard',
              style: TextStyle(
                fontSize: 14,
                color: elder?.subtitleText ?? const Color(0xFF94A3B8),
              ),
            ),
          ),
          const Expanded(child: SpringboardGrid()),
        ],
      ),
    );
  }
}
