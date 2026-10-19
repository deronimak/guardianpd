import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart' show TargetPlatform, debugPrint, defaultTargetPlatform, kIsWeb;

import 'parent_api_client.dart';

StreamSubscription<String>? _tokenRefreshSubscription;

/// Requests notification permission, obtains a real FCM device token, and
/// registers it with the backend (ARCHITECTURE.md §5 point 5).
///
/// Android and iOS (the `kIsWeb` guard below excludes web only) — Firebase
/// web needs its own service worker setup we haven't added.
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
    final isIos = defaultTargetPlatform == TargetPlatform.iOS;
    final platform = isIos ? 'ios' : 'android';

    final settings = await messaging.requestPermission();
    final authorized = settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
    if (!authorized) return;

    if (isIos) {
      // iOS shows banners only if told to while the app is open (otherwise a
      // parent with the app in front never sees the alert).
      await messaging.setForegroundNotificationPresentationOptions(alert: true, badge: true, sound: true);
      // FCM can only issue a token once Apple has handed the phone its APNs
      // token, which can take a few seconds after permission is granted.
      // Asking too early throws "apns-token-not-set", so wait for it.
      String? apnsToken;
      for (var attempt = 0; attempt < 20 && apnsToken == null; attempt++) {
        apnsToken = await messaging.getAPNSToken();
        if (apnsToken == null) await Future<void>.delayed(const Duration(milliseconds: 500));
      }
      if (apnsToken == null) {
        debugPrint('Push: no APNs token after 10s; push will not work on this device.');
        return;
      }
    }

    final token = await messaging.getToken();
    if (token == null) return;
    await client.registerDevice(token: token, platform: platform);

    // FCM rotates tokens from time to time; keep the backend's copy current,
    // or alerts silently stop reaching this phone.
    await _tokenRefreshSubscription?.cancel();
    _tokenRefreshSubscription = messaging.onTokenRefresh.listen((newToken) async {
      try {
        await client.registerDevice(token: newToken, platform: platform);
      } catch (e) {
        debugPrint('Push token refresh registration failed: $e');
      }
    });
  } catch (e) {
    debugPrint('Push registration failed (continuing without it): $e');
  }
}
