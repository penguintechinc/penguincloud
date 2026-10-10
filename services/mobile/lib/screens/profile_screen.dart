import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../widgets/adaptive_layout.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const AdaptiveLayout(
      phoneLayout: _PhoneProfile(),
      tabletLayout: _TabletProfile(),
    );
  }
}

class _PhoneProfile extends StatelessWidget {
  const _PhoneProfile();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: _ProfileContent(),
      ),
    );
  }
}

class _TabletProfile extends StatelessWidget {
  const _TabletProfile();

  @override
  Widget build(BuildContext context) {
    final elder = Theme.of(context).extension<ElderThemeData>();
    return SafeArea(
      child: Row(
        children: [
          SizedBox(
            width: 300,
            child: Container(
              color: elder?.cardBackground ?? const Color(0xFF1E293B),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _ProfileHeader(),
                  const Divider(),
                  const ListTile(
                    leading: Icon(Icons.person),
                    title: Text('Account'),
                    selected: true,
                  ),
                  const ListTile(
                    leading: Icon(Icons.security),
                    title: Text('Security'),
                  ),
                  const ListTile(
                    leading: Icon(Icons.notifications),
                    title: Text('Notifications'),
                  ),
                ],
              ),
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: _ProfileContent(),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileHeader extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final authProvider = context.watch<AuthProvider>();
    final user = authProvider.currentUser;
    final elder = Theme.of(context).extension<ElderThemeData>();

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          CircleAvatar(
            radius: 40,
            backgroundColor: elder?.primaryButton ?? const Color(0xFFF59E0B),
            child: Text(
              (user?.name ?? user?.email ?? 'U')[0].toUpperCase(),
              style: TextStyle(
                fontSize: 32,
                fontWeight: FontWeight.bold,
                color: elder?.primaryButtonText ?? const Color(0xFF0F172A),
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            user?.name ?? 'Unknown',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: elder?.titleText ?? const Color(0xFFFBBF24),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            user?.email ?? '',
            style: TextStyle(
              fontSize: 14,
              color: elder?.subtitleText ?? const Color(0xFF94A3B8),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProfileContent extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final authProvider = context.watch<AuthProvider>();
    final user = authProvider.currentUser;
    final elder = Theme.of(context).extension<ElderThemeData>();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ProfileHeader(),
        const SizedBox(height: 24),
        _buildSection('Account Information', [
          _buildInfoTile(
            context,
            icon: Icons.email,
            label: 'Email',
            value: user?.email ?? 'N/A',
          ),
          _buildInfoTile(
            context,
            icon: Icons.badge,
            label: 'Roles',
            value: user?.roles.join(', ') ?? 'None',
          ),
          _buildInfoTile(
            context,
            icon: Icons.fingerprint,
            label: 'User ID',
            value: user?.id ?? 'N/A',
          ),
        ], elder),
        const SizedBox(height: 32),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton.icon(
            onPressed: () => authProvider.logout(),
            icon: const Icon(Icons.logout),
            label: const Text('Sign Out'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFEF4444),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSection(
    String title,
    List<Widget> children,
    ElderThemeData? elder,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            color: elder?.titleText ?? const Color(0xFFFBBF24),
          ),
        ),
        const SizedBox(height: 12),
        ...children,
      ],
    );
  }

  Widget _buildInfoTile(
    BuildContext context, {
    required IconData icon,
    required String label,
    required String value,
  }) {
    final elder = Theme.of(context).extension<ElderThemeData>();
    return ListTile(
      leading: Icon(icon, color: elder?.labelText ?? const Color(0xFFFCD34D)),
      title: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          color: elder?.subtitleText ?? const Color(0xFF94A3B8),
        ),
      ),
      subtitle: Text(
        value,
        style: TextStyle(
          fontSize: 16,
          color: elder?.bodyText ?? const Color(0xFFCBD5E1),
        ),
      ),
      contentPadding: EdgeInsets.zero,
    );
  }
}
