import 'package:flutter/material.dart';

import '../parent/parent_login_screen.dart';
import '../staff/admin_login_screen.dart';
import '../staff/staff_login_screen.dart';

// Fixed-width wrapper only — the purple pill look itself comes from the
// app-wide ElevatedButtonTheme in main.dart, same as every other button.
class _RoleButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;
  const _RoleButton({required this.label, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 220,
      child: ElevatedButton(onPressed: onPressed, child: Text(label)),
    );
  }
}

class RoleSelectScreen extends StatelessWidget {
  const RoleSelectScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'School Attendance',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 64),
              _RoleButton(
                label: 'School Admin',
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AdminLoginScreen()),
                ),
              ),
              const SizedBox(height: 16),
              _RoleButton(
                label: 'School Staff',
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const StaffLoginScreen()),
                ),
              ),
              const SizedBox(height: 16),
              _RoleButton(
                label: 'Guardian',
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const ParentLoginScreen()),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
