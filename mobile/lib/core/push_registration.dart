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
/// Never throws — push is a nice-to-have, so the app keeps working if it fails.
/// Returns null on success, or a short plain-language reason the phone could
/// not be set up for notifications, which the parent home screen shows with a
/// Retry button (otherwise a failure is completely invisible).
Future<String?> initializeAndRegisterPush(ParentApiClient client) async {
  if (kIsWeb) return null;

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
    if (!authorized) {
      return 'Notifications are turned off for GuardianPD on this phone. '
          'Turn them on in the phone\'s Settings to get arrival alerts.';
    }

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
        return 'This iPhone could not get its Apple notification token (no-apns-token). '
            'Check that you are online, then tap Retry or reopen the app.';
      }
    }

    final token = await messaging.getToken();
    if (token == null) return 'No notification token was issued for this phone (no-fcm-token).';
    try {
      await client.registerDevice(token: token, platform: platform);
    } catch (e) {
      debugPrint('Push device registration failed: $e');
      return 'Could not register this phone with GuardianPD. Check your connection and tap Retry.';
    }

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
    return null;
  } catch (e) {
    debugPrint('Push registration failed (continuing without it): $e');
    final text = e.toString().replaceAll('\n', ' ');
    return 'Notification setup failed: ${text.length > 140 ? text.substring(0, 140) : text}';
  }
}
