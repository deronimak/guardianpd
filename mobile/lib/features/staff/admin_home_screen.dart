import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import 'add_staff_screen.dart';
import 'enroll_guardian_screen.dart';
import 'search_guardians_screen.dart';

// A tappable row with a small tinted icon badge — the "Lumen" home-screen
// treatment (see role_select_screen.dart for the rest of that direction),
// replacing a plain list of solid-purple buttons with something scannable
// at a glance.
class _ActionTile extends StatelessWidget {
  final IconData icon;
  final Color tint;
  final String label;
  final VoidCallback onTap;
  const _ActionTile({required this.icon, required this.tint, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final iconColor = Color.lerp(tint, Colors.black, 0.55)!;
    return Material(
      color: Theme.of(context).colorScheme.surface,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.black.withValues(alpha: 0.08)),
          ),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(color: tint, borderRadius: BorderRadius.circular(10)),
                child: Icon(icon, size: 18, color: iconColor),
              ),
              const SizedBox(width: 12),
              Expanded(child: Text(label, style: const TextStyle(fontSize: 14.5))),
              Icon(Icons.chevron_right, color: Colors.black.withValues(alpha: 0.3)),
            ],
          ),
        ),
      ),
    );
  }
}

class AdminHomeScreen extends StatelessWidget {
  final ApiClient apiClient;
  const AdminHomeScreen({super.key, required this.apiClient});

  Future<void> _changePassword(BuildContext context) async {
    final currentController = TextEditingController();
    final newController = TextEditingController();
    final result = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Change password'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: currentController,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Current password'),
            ),
            TextField(
              controller: newController,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'New password (min 8 chars)'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save')),
        ],
      ),
    );
    if (result != true) return;
    try {
      await apiClient.changeStaffPassword(currentController.text, newController.text);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Password changed.')));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Failed: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('School Admin')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _ActionTile(
              icon: Icons.person_add_alt,
              tint: const Color(0xFFEEEDFE),
              label: 'Add Guardian',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => EnrollGuardianScreen(apiClient: apiClient)),
              ),
            ),
            const SizedBox(height: 12),
            _ActionTile(
              icon: Icons.search,
              tint: const Color(0xFFFAECE7),
              label: 'Search Guardians',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => SearchGuardiansScreen(apiClient: apiClient)),
              ),
            ),
            const SizedBox(height: 12),
            _ActionTile(
              icon: Icons.badge_outlined,
              tint: const Color(0xFFE1F5EE),
              label: 'Add Staff Account',
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => AddStaffScreen(apiClient: apiClient)),
              ),
            ),
            const SizedBox(height: 20),
            Center(
              child: TextButton(
                onPressed: () => _changePassword(context),
                child: const Text('Change password'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
