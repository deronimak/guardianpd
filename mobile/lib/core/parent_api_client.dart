import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// Talks to the platform-level parent endpoints — no school slug involved,
/// since a parent's login identity spans every school their children
/// attend (ARCHITECTURE.md §2/§8), unlike the school-scoped ApiClient.
class ParentApiClient {
  static String get baseUrl => ApiClient.baseUrl;

  String? _parentToken;

  bool get isLoggedIn => _parentToken != null;

  Map<String, String> _headers() => {
        'Content-Type': 'application/json',
        if (_parentToken != null) 'Authorization': 'Bearer $_parentToken',
      };

  Future<void> activate({
    required String email,
    required String inviteToken,
    required String password,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/parent/activate'),
      headers: _headers(),
      body: jsonEncode({'email': email, 'invite_token': inviteToken, 'password': password}),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    _parentToken = jsonDecode(response.body)['access_token'] as String;
  }

  Future<void> login({required String email, required String password}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/parent/login'),
      headers: _headers(),
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    _parentToken = jsonDecode(response.body)['access_token'] as String;
  }

  Future<List<Map<String, dynamic>>> myChildren() async {
    final response = await http.get(Uri.parse('$baseUrl/parent/me/children'), headers: _headers());
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  /// Registers a push-notification device token. Requires the Flutter app
  /// to be wired up with a real Firebase project (firebase_messaging +
  /// google-services.json) to obtain an actual token — not set up in this
  /// scaffold; see README. The backend side (fan-out on scan) is ready to
  /// receive whatever token you pass here.
  Future<void> registerDevice({required String token, required String platform}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/parent/me/devices'),
      headers: _headers(),
      body: jsonEncode({'token': token, 'platform': platform}),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
  }
}
