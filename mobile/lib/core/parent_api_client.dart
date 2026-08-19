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

  /// Registers a push-notification device token (Android — see
  /// lib/core/push_registration.dart; iOS isn't wired up).
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

  Future<List<Map<String, dynamic>>> attendanceHistory({
    required String schoolSlug,
    required String studentId,
  }) async {
    final response = await http.get(
      Uri.parse('$baseUrl/parent/me/schools/$schoolSlug/students/$studentId/attendance'),
      headers: _headers(),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  Future<List<Map<String, dynamic>>> expectedAbsences({
    required String schoolSlug,
    required String studentId,
  }) async {
    final response = await http.get(
      Uri.parse('$baseUrl/parent/me/schools/$schoolSlug/students/$studentId/expected-absences'),
      headers: _headers(),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  /// [startDate]/[endDate] are sent as plain yyyy-MM-dd (matches Python's
  /// date.fromisoformat, which the backend's Pydantic schema expects).
  Future<void> markExpectedAbsence({
    required String schoolSlug,
    required String studentId,
    required DateTime startDate,
    required DateTime endDate,
    String? reason,
  }) async {
    String iso(DateTime d) =>
        '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
    final response = await http.post(
      Uri.parse('$baseUrl/parent/me/schools/$schoolSlug/students/$studentId/expected-absences'),
      headers: _headers(),
      body: jsonEncode({
        'start_date': iso(startDate),
        'end_date': iso(endDate),
        if (reason != null && reason.isNotEmpty) 'reason': reason,
      }),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
  }
}
