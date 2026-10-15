import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:path_provider/path_provider.dart';

/// Device-side storage for pupil-card scanning when the network is flaky:
///  - [queue]: scans captured while offline (or that failed to upload),
///    each with the time it physically happened, waiting to be synced.
///  - [roster]: pupil id -> name/class, so the gate screen can still show
///    who just tapped with no signal.
///  - [rejected]: scans the server refused on sync, kept so staff can see
///    what needs a manual record instead of it silently disappearing.
///  - pupil photos: cached as small files so the gate screen can show the
///    child's face (to compare with the card) even with no signal.
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
  // pupil id -> md5 of the photo we have cached, to re-download only on change.
  Map<String, String> photoHashes = {};
  final Map<String, Uint8List> _photoMemory = {};
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
        photoHashes = (data['photo_hashes'] as Map? ?? {}).map((k, v) => MapEntry(k as String, v as String));
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
      'photo_hashes': photoHashes,
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

  Future<void> enqueue(String token, DateTime scannedAt, {String? type}) async {
    queue.add({
      'token': token,
      'scanned_at': scannedAt.toUtc().toIso8601String(),
      if (type != null) 'type': type,
    });
    await _save();
  }

  /// A default for the arrived/leaving buttons when there is no connection:
  /// the opposite of this pupil's last saved scan today, else "arrived".
  String suggestedTypeFor(String pupilId, DateTime now) {
    String? lastType;
    DateTime? lastAt;
    for (final item in queue) {
      if (pupilIdFromToken(item['token'] as String) != pupilId) continue;
      final at = DateTime.tryParse(item['scanned_at'] as String)?.toLocal();
      if (at == null || at.year != now.year || at.month != now.month || at.day != now.day) continue;
      if (lastAt == null || at.isAfter(lastAt)) {
        lastAt = at;
        lastType = item['type'] as String?;
      }
    }
    return lastType == 'drop_off' ? 'pick_up' : 'drop_off';
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

  Future<Directory?> _photoDirectory() async {
    if (kIsWeb) return null;
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory('${base.path}/guardianpd_photos_$schoolSlug');
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  Future<Uint8List?> readPhoto(String pupilId) async {
    final cached = _photoMemory[pupilId];
    if (cached != null) return cached;
    try {
      final dir = await _photoDirectory();
      if (dir == null) return null;
      final file = File('${dir.path}/$pupilId.jpg');
      if (!await file.exists()) return null;
      final bytes = await file.readAsBytes();
      _photoMemory[pupilId] = bytes;
      return bytes;
    } catch (_) {
      return null;
    }
  }

  Future<void> savePhoto(String pupilId, Uint8List bytes, String? hash) async {
    _photoMemory[pupilId] = bytes;
    if (hash != null) photoHashes[pupilId] = hash;
    try {
      final dir = await _photoDirectory();
      if (dir != null) await File('${dir.path}/$pupilId.jpg').writeAsBytes(bytes, flush: true);
    } catch (_) {}
    await _save();
  }

  /// Pupils whose photo exists on the server but isn't cached yet (or has changed).
  List<Map<String, dynamic>> pupilsNeedingPhoto() => roster.values
      .where((p) => p['photo_hash'] != null && photoHashes[p['id']] != p['photo_hash'])
      .toList();

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
