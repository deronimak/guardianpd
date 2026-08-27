import 'dart:async';
import 'dart:ui';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import 'package:flutter/material.dart';

import 'features/auth/role_select_screen.dart';

Future<void> main() async {
  runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();

    // Android-only, same platform gate as lib/core/push_registration.dart —
    // this dev setup has no Firebase web/iOS config yet.
    if (!kIsWeb) {
      await Firebase.initializeApp();
      // Crash reports are noise in local dev; only report from real builds.
      await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(!kDebugMode);
      FlutterError.onError = FirebaseCrashlytics.instance.recordFlutterFatalError;
      PlatformDispatcher.instance.onError = (error, stack) {
        FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
        return true;
      };
    }

    runApp(const MyApp());
  }, (error, stack) {
    if (!kIsWeb) {
      FirebaseCrashlytics.instance.recordError(error, stack, fatal: true);
    }
  });
}

// Single source of truth for button styling — every ElevatedButton,
// OutlinedButton, and TextButton in the app resolves to this same solid
// purple pill via the theme below, so individual screens never need their
// own button styles to stay consistent with each other.
const _brandPurple = Color(0xFF6A4FE0);

// Fully rounded "pill" shape — the "Lumen" look (see role_select_screen.dart
// and admin_home_screen.dart for the rest of that direction: a circular
// icon badge and tiered/tinted button and tile colors built from this same
// brand purple).
const _buttonShape = StadiumBorder();
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

// Very pale tint of the brand purple — the fill for every text field
// app-wide (see inputDecorationTheme below), so forms read as soft rounded
// wells rather than the Material-default underline, matching the rounded
// cards and pill buttons everywhere else in the Lumen direction.
final _fieldFill = Color.lerp(_brandPurple, Colors.white, 0.94)!;

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
        cardTheme: CardThemeData(
          elevation: 0,
          color: Colors.white,
          surfaceTintColor: Colors.transparent,
          margin: const EdgeInsets.only(bottom: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(color: Colors.black.withValues(alpha: 0.08)),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: _fieldFill,
          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
          disabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(14),
            borderSide: const BorderSide(color: _brandPurple, width: 1.5),
          ),
          errorBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
        ),
      ),
      home: const RoleSelectScreen(),
    );
  }
}
