import 'package:flutter/material.dart';

class SpringboardItem {
  const SpringboardItem({
    required this.title,
    required this.icon,
    required this.route,
    this.description,
    this.roles,
    this.category,
  });

  final String title;
  final IconData icon;
  final String route;
  final String? description;
  final List<String>? roles;
  final String? category;

  bool isVisibleTo(List<String> userRoles) {
    if (roles == null || roles!.isEmpty) return true;
    return userRoles.any((r) => roles!.contains(r));
  }
}
