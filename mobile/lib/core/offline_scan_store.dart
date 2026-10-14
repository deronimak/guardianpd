import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path_provider/path_provider.dart';

/// Device-side storage for pupil-card scanning when the network is flaky:
///  - [queue]: scans captured while offline (or that failed to upload),
///    each with the time it physically happened, waiting to be synced.
///  - [roster]: pupil id -> name/class, so the gate screen can still show
///    who just tapped with no signal.
///  - [rejected]: scans the server refused on sync, kept so staff can see
///    what needs a manual record instead of it silently disappearing.
///  - [credentialMode]: the school's mode, so the right home screen shows
///    even when the profile call can't be made.
///
/// Persisted as one small JSON file per school (survives app restarts and
/// reboots). On web (only used for dev previews) it falls back to memory.
class OfflineScanStore {
  static final Map<String, OfflineScanStore> _instances = {};
  static final Map<String, String> _webMemory = {};

  final String schoolSlug;
  OfflineScanStore._(this.schoolSlug);

  factory OfflineScanStore.forSchool(String slug) =>
      _instances.putIfAbsent(slug, () => OfflineScanStore._(slug));

  bool _loaded = false;
  List<Map<String, dynamic>> queue = [];
  List<Map<String, dynamic>> rejected = [];
  Map<String, Map<String, dynamic>> roster = {};
  String? credentialMode;

  Future<void> _writeChain = Future.value();

  Future<File?> _file() async {
    if (kIsWeb) return null;
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/guardianpd_offline_$schoolSlug.json');
  }

  Future<void> load() async {
    if (_loaded) return;
    try {
      String? raw;
      final file = await _file();
      if (file == null) {
        raw = _webMemory[schoolSlug];
      } else if (await file.exists()) {
        raw = await file.readAsString();
      }
      if (raw != null && raw.isNotEmpty) {
        final data = jsonDecode(raw) as Map<String, dynamic>;
        queue = (data['queue'] as List? ?? []).cast<Map<String, dynamic>>();
        rejected = (data['rejected'] as List? ?? []).cast<Map<String, dynamic>>();
        roster = (data['roster'] as Map? ?? {}).map(
          (k, v) => MapEntry(k as String, (v as Map).cast<String, dynamic>()),
        );
        credentialMode = data['credential_mode'] as String?;
      }
    } catch (_) {
      // A corrupt/unreadable file must never stop scanning: start empty.
    }
    _loaded = true;
  }

  Future<void> _save() {
    final snapshot = jsonEncode({
      'queue': queue,
      'rejected': rejected,
      'roster': roster,
      'credential_mode': credentialMode,
    });
    _writeChain = _writeChain.then((_) async {
      try {
        final file = await _file();
        if (file == null) {
          _webMemory[schoolSlug] = snapshot;
        } else {
          await file.writeAsString(snapshot, flush: true);
        }
      } catch (_) {}
    });
    return _writeChain;
  }

  Future<void> enqueue(String token, DateTime scannedAt) async {
    queue.add({'token': token, 'scanned_at': scannedAt.toUtc().toIso8601String()});
    await _save();
  }

  /// Applies the server's per-item results (same order as [sent]) after a
  /// batch upload: accepted/duplicate items leave the queue, rejected ones
  /// move to [rejected] for staff to review.
  Future<void> applyBatchResults(List<Map<String, dynamic>> sent, List<Map<String, dynamic>> results) async {
    for (var i = 0; i < sent.length && i < results.length; i++) {
      final result = results[i];
      queue.remove(sent[i]);
      if (result['status'] == 'rejected') {
        rejected.add({
          'scanned_at': sent[i]['scanned_at'],
          'detail': result['detail'] ?? 'Rejected',
          'name': nameForToken(sent[i]['token'] as String),
        });
      }
    }
    await _save();
  }

  Future<void> clearRejected() async {
    rejected = [];
    await _save();
  }

  Future<void> setRoster(List<Map<String, dynamic>> entries) async {
    roster = {for (final e in entries) e['id'] as String: e};
    await _save();
  }

  Future<void> setCredentialMode(String mode) async {
    credentialMode = mode;
    await _save();
  }

  /// The pupil id inside a card's QR token, WITHOUT verifying the signature
  /// (the key never leaves the server). Only used to show a name offline;
  /// the server validates the real signature when the scan is uploaded.
  static String? pupilIdFromToken(String token) {
    try {
      final payloadPart = token.split('.').first;
      final padded = payloadPart.padRight(payloadPart.length + (4 - payloadPart.length % 4) % 4, '=');
      final json = jsonDecode(utf8.decode(base64Url.decode(padded))) as Map<String, dynamic>;
      return json['pid'] as String?;
    } catch (_) {
      return null;
    }
  }

  String? nameForToken(String token) {
    final pid = pupilIdFromToken(token);
    return pid == null ? null : roster[pid]?['name'] as String?;
  }
}
