import 'dart:convert';

import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform, kIsWeb;
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// Talks to the FastAPI backend. Every request carries the school slug so
/// the API can route to that school's tenant database (ARCHITECTURE.md §2).
class ApiClient {
  // Only the Android emulator needs the 10.0.2.2 alias to reach the host
  // machine; web/desktop/iOS-simulator all reach it via localhost. Change
  // this for a physical device (use your machine's LAN IP) or a deployed
  // backend in production.
  static String get baseUrl {
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
  }

  final String schoolSlug;
  String? _staffToken;

  ApiClient({required this.schoolSlug});

  bool get isStaffLoggedIn => _staffToken != null;

  Map<String, String> _headers({bool authenticated = false}) => {
        'Content-Type': 'application/json',
        'X-School-Slug': schoolSlug,
        if (authenticated && _staffToken != null) 'Authorization': 'Bearer $_staffToken',
      };

  Future<void> staffLogin(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/staff/login'),
      headers: _headers(),
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    _staffToken = jsonDecode(response.body)['access_token'] as String;
  }

  /// School-initiated guardian enrollment (ARCHITECTURE.md §8): creates the
  /// guardian, issues their QR credential, and emails them an activation
  /// invite. Returns the new guardian's id/name/qr_token.
  Future<Map<String, dynamic>> createGuardian({
    required String name,
    required String email,
    String? phone,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/guardians'),
      headers: _headers(authenticated: true),
      body: jsonEncode({'name': name, 'email': email, if (phone != null && phone.isNotEmpty) 'phone': phone}),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Fetches the printed QR credential PDF for a guardian, to hand off to
  /// the OS share sheet (see enroll_guardian_screen.dart).
  Future<List<int>> downloadQrCredentialPdf(String guardianId) async {
    final response = await http.get(
      Uri.parse('$baseUrl/guardians/$guardianId/qr-credential.pdf'),
      headers: _headers(authenticated: true),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return response.bodyBytes;
  }

  /// Scans a guardian's QR credential for one child. See the security flow
  /// in ARCHITECTURE.md §5/§6 — this simply forwards to the backend, which
  /// does the signature/revocation/authorization checks.
  Future<Map<String, dynamic>> scanQr({
    required String qrToken,
    required String studentId,
    required String type,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/attendance/scan'),
      headers: _headers(authenticated: true),
      body: jsonEncode({'token': qrToken, 'student_id': studentId, 'type': type}),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }
}
