import 'package:flutter/material.dart';

import 'features/auth/role_select_screen.dart';

void main() {
  runApp(const MyApp());
}

// Single source of truth for button styling — every ElevatedButton,
// OutlinedButton, and TextButton in the app resolves to this same solid
// purple pill via the theme below, so individual screens never need their
// own button styles to stay consistent with each other.
const _brandPurple = Color(0xFF6A4FE0);

final _buttonShape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(10));
const _buttonPadding = EdgeInsets.symmetric(horizontal: 24, vertical: 14);
const _buttonTextStyle = TextStyle(fontSize: 16, fontWeight: FontWeight.w500);

ButtonStyle _uniformButtonStyle() => ElevatedButton.styleFrom(
      backgroundColor: _brandPurple,
      foregroundColor: Colors.white,
      disabledBackgroundColor: _brandPurple.withValues(alpha: 0.4),
      disabledForegroundColor: Colors.white70,
      elevation: 0,
      padding: _buttonPadding,
      shape: _buttonShape,
      textStyle: _buttonTextStyle,
    );

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GuardianPD',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: _brandPurple),
        elevatedButtonTheme: ElevatedButtonThemeData(style: _uniformButtonStyle()),
        outlinedButtonTheme: OutlinedButtonThemeData(style: _uniformButtonStyle()),
        textButtonTheme: TextButtonThemeData(style: _uniformButtonStyle()),
      ),
      home: const RoleSelectScreen(),
    );
  }
}
