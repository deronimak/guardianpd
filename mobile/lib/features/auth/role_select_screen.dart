import 'package:flutter/material.dart';

import '../parent/parent_login_screen.dart';
import '../staff/admin_login_screen.dart';
import '../staff/staff_login_screen.dart';

// Solid-fill purple pill, shared by all three role buttons so they read as
// one consistent button style rather than a primary/outlined mix.
class _RoleButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;
  const _RoleButton({required this.label, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 220,
      height: 48,
      child: ElevatedButton(
        onPressed: onPressed,
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF6A4FE0),
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
        child: Text(label, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500)),
      ),
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
