import 'package:flutter/material.dart';

import '../utils/constants.dart';

class AdaptiveLayout extends StatelessWidget {
  const AdaptiveLayout({
    super.key,
    required this.phoneLayout,
    required this.tabletLayout,
  });

  final Widget phoneLayout;
  final Widget tabletLayout;

  static bool isTablet(BoxConstraints constraints) =>
      constraints.maxWidth >= AppConstants.phoneBreakpoint;

  static bool isTabletLandscape(BoxConstraints constraints) =>
      constraints.maxWidth >= AppConstants.tabletLandscapeBreakpoint;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (isTablet(constraints)) {
          return tabletLayout;
        }
        return phoneLayout;
      },
    );
  }
}
