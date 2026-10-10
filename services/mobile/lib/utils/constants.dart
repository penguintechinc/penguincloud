import 'package:flutter/material.dart';

import '../models/springboard_item.dart';

abstract final class AppConstants {
  static const double phoneBreakpoint = 600;
  static const double tabletLandscapeBreakpoint = 900;
  static const int phoneGridColumns = 2;
  static const int tabletGridColumns = 3;
  static const int tabletLandscapeGridColumns = 4;
  static const double gridSpacing = 16;
  static const double tileAspectRatio = 1.1;
  static const String tokenKey = 'auth_token';
  static const String refreshTokenKey = 'refresh_token';
  static const String userKey = 'user_data';

  static const List<SpringboardItem> defaultItems = [
    SpringboardItem(
      title: 'Dashboard',
      icon: Icons.dashboard,
      route: '/dashboard',
      description: 'System overview and metrics',
      category: 'General',
    ),
    SpringboardItem(
      title: 'Users',
      icon: Icons.people,
      route: '/users',
      description: 'User management',
      roles: ['admin'],
      category: 'Administration',
    ),
    SpringboardItem(
      title: 'Teams',
      icon: Icons.groups,
      route: '/teams',
      description: 'Team management',
      category: 'General',
    ),
    SpringboardItem(
      title: 'Settings',
      icon: Icons.settings,
      route: '/settings',
      description: 'Application settings',
      roles: ['admin', 'maintainer'],
      category: 'Administration',
    ),
    SpringboardItem(
      title: 'Monitoring',
      icon: Icons.monitor_heart,
      route: '/monitoring',
      description: 'System health and metrics',
      roles: ['admin', 'maintainer'],
      category: 'Operations',
    ),
    SpringboardItem(
      title: 'Logs',
      icon: Icons.article,
      route: '/logs',
      description: 'Application logs',
      roles: ['admin', 'maintainer'],
      category: 'Operations',
    ),
  ];
}
