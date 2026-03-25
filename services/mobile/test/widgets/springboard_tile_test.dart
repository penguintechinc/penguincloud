import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/models/springboard_item.dart';
import 'package:mobile/widgets/springboard_tile.dart';

void main() {
  const testItem = SpringboardItem(
    title: 'Dashboard',
    icon: Icons.dashboard,
    route: '/dashboard',
    description: 'System overview',
  );

  Widget buildTestWidget({VoidCallback? onTap}) {
    return MaterialApp(
      theme: ThemeData.dark().copyWith(
        extensions: const [ElderThemeData.dark],
      ),
      home: Scaffold(
        body: SpringboardTile(
          item: testItem,
          onTap: onTap ?? () {},
        ),
      ),
    );
  }

  group('SpringboardTile', () {
    testWidgets('renders title and description', (tester) async {
      await tester.pumpWidget(buildTestWidget());

      expect(find.text('Dashboard'), findsOneWidget);
      expect(find.text('System overview'), findsOneWidget);
    });

    testWidgets('renders icon', (tester) async {
      await tester.pumpWidget(buildTestWidget());

      expect(find.byIcon(Icons.dashboard), findsOneWidget);
    });

    testWidgets('calls onTap when tapped', (tester) async {
      var tapped = false;
      await tester.pumpWidget(buildTestWidget(onTap: () => tapped = true));

      await tester.tap(find.byType(InkWell));
      expect(tapped, isTrue);
    });

    testWidgets('renders without description', (tester) async {
      const noDescItem = SpringboardItem(
        title: 'Settings',
        icon: Icons.settings,
        route: '/settings',
      );
      await tester.pumpWidget(MaterialApp(
        theme: ThemeData.dark().copyWith(
          extensions: const [ElderThemeData.dark],
        ),
        home: Scaffold(
          body: SpringboardTile(
            item: noDescItem,
            onTap: () {},
          ),
        ),
      ));

      expect(find.text('Settings'), findsOneWidget);
    });
  });
}
