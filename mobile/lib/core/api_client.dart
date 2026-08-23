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
  String? _role;

  ApiClient({required this.schoolSlug});

  bool get isStaffLoggedIn => _staffToken != null;
  // "admin" (School Admin) or "staff" (School Staff) — set by staffLogin,
  // lets the UI branch to the right home screen and reject a login attempt
  // through the wrong role's button (GuardianPD spec splits the two).
  String? get role => _role;

  Map<String, String> _headers({bool authenticated = false}) => {
        'Content-Type': 'application/json',
        'X-School-Slug': schoolSlug,
        if (authenticated && _staffToken != null) 'Authorization': 'Bearer $_staffToken',
      };

  /// Returns the account's role ("admin" / "staff") so the caller can
  /// verify it matches the login screen the user actually tapped.
  Future<String> staffLogin(String email, String password) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/staff/login'),
      headers: _headers(),
      body: jsonEncode({'email': email, 'password': password}),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    _staffToken = body['access_token'] as String;
    _role = body['role'] as String;
    return _role!;
  }

  Future<void> changeStaffPassword(String currentPassword, String newPassword) async {
    final response = await http.post(
      Uri.parse('$baseUrl/auth/staff/change-password'),
      headers: _headers(authenticated: true),
      body: jsonEncode({'current_password': currentPassword, 'new_password': newPassword}),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
  }

  /// School-Admin-initiated combined enrollment (GuardianPD spec): creates
  /// the guardian, issues their QR credential, and (via [childrenNames])
  /// up to 10 named children in one call. Returns the new guardian's
  /// id/name/qr_token plus the created children.
  Future<Map<String, dynamic>> createGuardian({
    required String name,
    required String email,
    String? phone,
    List<String> childrenNames = const [],
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/guardians'),
      headers: _headers(authenticated: true),
      body: jsonEncode({
        'name': name,
        'email': email,
        if (phone != null && phone.isNotEmpty) 'phone': phone,
        'children': childrenNames.map((n) => {'name': n}).toList(),
      }),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// School Admin "search guardians" screen — print QR credentials and
  /// resend activation links both start from a search result.
  Future<List<Map<String, dynamic>>> searchGuardians(String query) async {
    final response = await http.get(
      Uri.parse('$baseUrl/guardians?query=${Uri.encodeQueryComponent(query)}'),
      headers: _headers(authenticated: true),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  Future<void> resendActivation(String guardianId) async {
    final response = await http.post(
      Uri.parse('$baseUrl/guardians/$guardianId/resend-activation'),
      headers: _headers(authenticated: true),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
  }

  Future<void> createStaffAccount({required String username, required String password}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/staff'),
      headers: _headers(authenticated: true),
      body: jsonEncode({'username': username, 'password': password}),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
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

  /// Lists students at this school, for the "link an existing guardian to
  /// another student" picker — the combined guardian+children form is the
  /// primary enrollment path, but this stays available for adding a later
  /// sibling to an already-enrolled guardian.
  Future<List<Map<String, dynamic>>> listStudents() async {
    final response = await http.get(
      Uri.parse('$baseUrl/students'),
      headers: _headers(authenticated: true),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> createStudent({required String name, String? grade}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/students'),
      headers: _headers(authenticated: true),
      body: jsonEncode({'name': name, if (grade != null && grade.isNotEmpty) 'grade': grade}),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  /// Many-to-many guardian<->student authorization link (ARCHITECTURE.md §3)
  /// — who's allowed to drop off/pick up which children.
  Future<void> linkGuardianToStudent({
    required String studentId,
    required String guardianId,
    String? relationship,
    bool isAuthorizedPickup = true,
  }) async {
    final response = await http.post(
      Uri.parse('$baseUrl/students/$studentId/guardians/$guardianId'),
      headers: _headers(authenticated: true),
      body: jsonEncode({
        if (relationship != null && relationship.isNotEmpty) 'relationship': relationship,
        'is_authorized_pickup': isAuthorizedPickup,
      }),
    );
    if (response.statusCode != 201) {
      throw ApiException(response.statusCode, response.body);
    }
  }

  /// Looks up which students a scanned guardian is authorized for, so staff
  /// can pick the right child before recording the attendance event. This
  /// is a read-only convenience — POST /attendance/scan independently
  /// re-verifies authorization regardless of what this returns.
  Future<Map<String, dynamic>> lookupGuardianByQr(String qrToken) async {
    final response = await http.get(
      Uri.parse('$baseUrl/guardians/lookup?token=${Uri.encodeQueryComponent(qrToken)}'),
      headers: _headers(authenticated: true),
    );
    if (response.statusCode != 200) {
      throw ApiException(response.statusCode, response.body);
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
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
