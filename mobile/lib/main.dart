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
