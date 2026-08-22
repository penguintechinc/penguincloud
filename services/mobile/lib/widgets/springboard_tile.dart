import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';

import '../models/springboard_item.dart';

class SpringboardTile extends StatelessWidget {
  const SpringboardTile({super.key, required this.item, required this.onTap});

  final SpringboardItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final elder = Theme.of(context).extension<ElderThemeData>();

    return Card(
      color: elder?.cardBackground ?? const Color(0xFF1E293B),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: elder?.cardBorder ?? const Color(0xFF334155)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                item.icon,
                size: 40,
                color: elder?.titleText ?? const Color(0xFFFBBF24),
              ),
              const SizedBox(height: 12),
              Text(
                item.title,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: elder?.titleText ?? const Color(0xFFFBBF24),
                ),
                textAlign: TextAlign.center,
              ),
              if (item.description != null) ...[
                const SizedBox(height: 4),
                Text(
                  item.description!,
                  style: TextStyle(
                    fontSize: 12,
                    color: elder?.subtitleText ?? const Color(0xFF94A3B8),
                  ),
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
