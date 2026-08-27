import 'package:flutter/material.dart';

import '../parent/parent_login_screen.dart';
import '../staff/admin_login_screen.dart';
import '../staff/staff_login_screen.dart';

const _brandPurple = Color(0xFF6A4FE0);
// Tinted down from _brandPurple, not a separate hue — keeps the three role
// buttons visually tiered (primary/secondary/tertiary) while staying tied
// to the same brand color, the "Lumen" direction (see main.dart).
final _secondaryPurple = Color.lerp(_brandPurple, Colors.white, 0.35)!;
final _tertiaryPurple = Color.lerp(_brandPurple, Colors.white, 0.88)!;
final _onTertiaryPurple = Color.lerp(_brandPurple, Colors.black, 0.25)!;

// Fixed-width wrapper — shape/radius still comes from the app-wide
// ElevatedButtonTheme in main.dart (a pill/StadiumBorder), only the fill
// and text colors are overridden per tier here.
class _RoleButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onPressed;
  final ButtonStyle? style;
  const _RoleButton({required this.label, required this.icon, required this.onPressed, this.style});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 240,
      child: ElevatedButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 18),
        label: Text(label),
        style: style,
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
              Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(color: _brandPurple, shape: BoxShape.circle),
                child: const Icon(Icons.shield_moon_outlined, color: Colors.white, size: 28),
              ),
              const SizedBox(height: 20),
              const Text(
                'School Attendance',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 48),
              _RoleButton(
                label: 'School Admin',
                icon: Icons.admin_panel_settings_outlined,
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AdminLoginScreen()),
                ),
              ),
              const SizedBox(height: 12),
              _RoleButton(
                label: 'School Staff',
                icon: Icons.groups_outlined,
                style: ElevatedButton.styleFrom(backgroundColor: _secondaryPurple, foregroundColor: _onTertiaryPurple),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const StaffLoginScreen()),
                ),
              ),
              const SizedBox(height: 12),
              _RoleButton(
                label: 'Guardian',
                icon: Icons.favorite_border,
                style: ElevatedButton.styleFrom(backgroundColor: _tertiaryPurple, foregroundColor: _onTertiaryPurple),
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
