import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show debugPrint, kIsWeb;

import 'parent_api_client.dart';

/// Requests notification permission, obtains a real FCM device token, and
/// registers it with the backend (ARCHITECTURE.md §5 point 5).
///
/// Android-only for now: Firebase web needs its own service worker setup
/// we haven't added, and this dev machine has no way to build/test iOS.
///
/// Failures here are swallowed (logged only) — push notifications are a
/// nice-to-have; a parent should still be able to use the app if
/// registration fails for some reason (e.g. no google-services.json yet).
Future<void> initializeAndRegisterPush(ParentApiClient client) async {
  if (kIsWeb) return;

  try {
    // Already initialized in main.dart on a normal app launch — this guard
    // just makes the function safe to call standalone (e.g. from tests).
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }

    final messaging = FirebaseMessaging.instance;
    final settings = await messaging.requestPermission();
    final authorized = settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
    if (!authorized) return;

    final token = await messaging.getToken();
    if (token == null) return;

    await client.registerDevice(token: token, platform: 'android');
  } catch (e) {
    debugPrint('Push registration failed (continuing without it): $e');
  }
}
