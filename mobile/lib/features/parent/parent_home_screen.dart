import 'package:flutter/material.dart';

/// Placeholder for the parent experience (ARCHITECTURE.md §10): linked
/// children across schools, attendance history, planned-absence marking,
/// notification preferences. The printed QR credential itself is generated
/// and handed out by school staff at enrollment (§8) — parents don't
/// generate or manage it from this screen.
class ParentHomeScreen extends StatelessWidget {
  const ParentHomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Children')),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Not yet built: linked children list, attendance history, '
            'planned-absence marking, notification preferences.',
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}
