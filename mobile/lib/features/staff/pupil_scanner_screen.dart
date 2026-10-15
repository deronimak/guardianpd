import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api_client.dart';
import '../../core/offline_scan_store.dart';

enum _Outcome { recorded, saved, duplicate, rejected, blocked }

class _ScanFeedback {
  final _Outcome outcome;
  final String title;
  final String? subtitle;
  final String? note;
  // The child's face, so gate staff can compare it with who is standing there.
  final Uint8List? photo;
  const _ScanFeedback(this.outcome, this.title, {this.subtitle, this.note, this.photo});
}

/// A scanned card waiting for the user to choose what to record.
class _PendingScan {
  final String token;
  final String name;
  final String? grade;
  final Uint8List? photo;
  final String suggested;
  final String? lastNote;
  final bool offline;
  final DateTime when;
  const _PendingScan({
    required this.token,
    required this.name,
    required this.suggested,
    required this.offline,
    required this.when,
    this.grade,
    this.photo,
    this.lastNote,
  });
}

String _typeLabel(String type) => type == 'drop_off' ? 'Arrived at school' : 'Leaving school';

/// Scans pupil ID cards. Works for both a staff member scanning with their
/// own phone and a fixed "gate station" (a phone/tablet left at the gate):
/// [station] just locks the screen to scanning with big result feedback.
///
/// Offline-first: if the network is down (or the request times out) the scan
/// is saved on the device with its real time and uploaded automatically once
/// the connection returns, so a signal drop never loses attendance.
class PupilScannerScreen extends StatefulWidget {
  final ApiClient apiClient;
  final bool station;
  const PupilScannerScreen({super.key, required this.apiClient, this.station = false});

  @override
  State<PupilScannerScreen> createState() => _PupilScannerScreenState();
}

class _PupilScannerScreenState extends State<PupilScannerScreen> {
  late final OfflineScanStore _store = OfflineScanStore.forSchool(widget.apiClient.schoolSlug);
  final _manualTokenController = TextEditingController();

  late bool _station = widget.station;
  _ScanFeedback? _feedback;
  // Set between scanning a card and the user choosing arrived/leaving.
  _PendingScan? _pending;
  Timer? _clearTimer;
  Timer? _syncTimer;
  bool _syncing = false;
  bool _ready = false;
  bool _online = true;
  bool _sessionExpired = false;
  bool _syncingPhotos = false;
  // Station mode is locked with a PIN chosen by the staff member who starts
  // it; kept only in memory, so closing the app also ends station mode.
  String? _stationPin;

  // Same card seen again by the camera within this window is ignored client
  // side (the camera reads a held card many times a second). The server has
  // its own, longer, duplicate window.
  static const _localDebounce = Duration(seconds: 8);
  final Map<String, DateTime> _recentTokens = {};

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    await _store.load();
    if (_station && !await _ensurePin()) {
      if (mounted) Navigator.of(context).pop();
      return;
    }
    if (mounted) setState(() => _ready = true);
    unawaited(_refreshRoster());
    unawaited(_syncQueue());
    _syncTimer = Timer.periodic(const Duration(seconds: 30), (_) => _syncQueue());
  }

  @override
  void dispose() {
    _clearTimer?.cancel();
    _syncTimer?.cancel();
    _manualTokenController.dispose();
    super.dispose();
  }

  static bool _isNetworkError(Object e) => e is! ApiException;

  static String _detail(ApiException e) {
    try {
      final body = jsonDecode(e.message);
      final detail = body is Map ? body['detail'] : null;
      if (detail is String) return detail;
    } catch (_) {}
    return 'Something went wrong (${e.statusCode})';
  }

  Future<void> _refreshRoster() async {
    try {
      final roster = await widget.apiClient.pupilRoster();
      await _store.setRoster(roster);
      if (mounted) setState(() => _online = true);
      unawaited(_syncPhotos());
    } catch (e) {
      if (e is ApiException && e.statusCode == 401) _sessionExpired = true;
    }
  }

  /// Downloads pupil photos we don't have yet (or that changed), one at a
  /// time in the background, so they show at the gate even when offline.
  Future<void> _syncPhotos() async {
    if (_syncingPhotos) return;
    _syncingPhotos = true;
    try {
      for (final pupil in _store.pupilsNeedingPhoto()) {
        final bytes = await widget.apiClient.fetchPupilPhoto(pupil['id'] as String);
        if (bytes != null) await _store.savePhoto(pupil['id'] as String, bytes, pupil['photo_hash'] as String?);
      }
    } catch (_) {
      // Offline or a hiccup: the rest is picked up on the next sync.
    } finally {
      _syncingPhotos = false;
    }
  }

  Future<Uint8List?> _photoFor(String? pupilId, bool serverHasPhoto) async {
    if (pupilId == null) return null;
    final cached = await _store.readPhoto(pupilId);
    if (cached != null || !serverHasPhoto) return cached;
    try {
      final bytes = await widget.apiClient.fetchPupilPhoto(pupilId).timeout(const Duration(seconds: 3));
      if (bytes != null) await _store.savePhoto(pupilId, bytes, null);
      return bytes;
    } catch (_) {
      return null;
    }
  }

  /// Asks the supervising staff member to choose a PIN for station mode.
  /// Returns false if they cancel.
  Future<bool> _ensurePin() async {
    if (_stationPin != null) return true;
    final first = TextEditingController();
    final second = TextEditingController();
    String? error;
    final pin = await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Set a station PIN'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('You will need this PIN to leave station mode. Do not share it with pupils.'),
              TextField(
                controller: first,
                keyboardType: TextInputType.number,
                obscureText: true,
                maxLength: 4,
                decoration: const InputDecoration(labelText: '4-digit PIN', counterText: ''),
              ),
              TextField(
                controller: second,
                keyboardType: TextInputType.number,
                obscureText: true,
                maxLength: 4,
                decoration: const InputDecoration(labelText: 'Repeat PIN', counterText: ''),
              ),
              if (error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(error!, style: const TextStyle(color: Colors.red))),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            TextButton(
              onPressed: () {
                if (!RegExp(r'^\d{4}$').hasMatch(first.text)) {
                  setLocal(() => error = 'Enter exactly 4 digits');
                } else if (first.text != second.text) {
                  setLocal(() => error = 'The PINs do not match');
                } else {
                  Navigator.pop(ctx, first.text);
                }
              },
              child: const Text('Start'),
            ),
          ],
        ),
      ),
    );
    first.dispose();
    second.dispose();
    if (pin == null) return false;
    _stationPin = pin;
    return true;
  }

  Future<void> _syncQueue() async {
    if (_syncing || _store.queue.isEmpty) return;
    _syncing = true;
    if (mounted) setState(() {});
    try {
      final sent = List<Map<String, dynamic>>.from(_store.queue);
      final results = await widget.apiClient.pupilScanBatch(sent);
      await _store.applyBatchResults(sent, results);
      _sessionExpired = false;
      if (mounted) setState(() => _online = true);
      unawaited(_refreshRoster());
    } on ApiException catch (e) {
      if (e.statusCode == 401) _sessionExpired = true;
      // Other server answers (e.g. subscription inactive): keep the queue.
    } catch (_) {
      if (mounted) setState(() => _online = false);
    } finally {
      _syncing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _handleDetection(BarcodeCapture capture) async {
    if (!_ready || _pending != null || capture.barcodes.isEmpty) return;
    final raw = capture.barcodes.first.rawValue;
    if (raw == null) return;
    await _processToken(raw);
  }

  Future<void> _processToken(String token) async {
    final now = DateTime.now();
    final last = _recentTokens[token];
    if (last != null && now.difference(last) < _localDebounce) return;
    _recentTokens[token] = now;
    _recentTokens.removeWhere((_, t) => now.difference(t) > const Duration(minutes: 2));

    // A guardian card (or any other QR) is not a pupil card — say so at
    // once instead of waiting for the server.
    if (OfflineScanStore.pupilIdFromToken(token) == null) {
      _show(const _ScanFeedback(_Outcome.rejected, 'Not a pupil card', subtitle: 'This QR code is not a pupil ID card'));
      return;
    }

    try {
      final info = await widget.apiClient.pupilLookup(token);
      _sessionExpired = false;
      if (mounted) setState(() => _online = true);
      final photo = await _photoFor(info['student_id'] as String?, info['has_photo'] == true);
      final lastType = info['last_type'] as String?;
      final lastTime = info['last_time'] as String?;
      _prompt(_PendingScan(
        token: token,
        name: info['student_name'] as String? ?? 'Pupil',
        grade: info['grade'] as String?,
        photo: photo,
        suggested: info['suggested_type'] as String? ?? 'drop_off',
        lastNote: lastType == null || lastTime == null
            ? null
            : (lastType == 'drop_off' ? 'Arrived at $lastTime today' : 'Left at $lastTime today'),
        offline: false,
        when: now,
      ));
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        // Login expired: don't lose the scan. Let them record it and save it.
        _sessionExpired = true;
        await _promptOffline(token, now);
      } else if (e.statusCode == 402 || e.statusCode == 403) {
        _show(_ScanFeedback(_Outcome.blocked, 'Scanning unavailable', subtitle: _detail(e)));
      } else {
        _show(_ScanFeedback(_Outcome.rejected, 'Card not accepted', subtitle: _detail(e)));
      }
    } catch (e) {
      if (_isNetworkError(e)) {
        if (mounted) setState(() => _online = false);
        await _promptOffline(token, now);
      }
    }
  }

  /// No connection: identify the pupil from the cached list instead.
  Future<void> _promptOffline(String token, DateTime now) async {
    final pupilId = OfflineScanStore.pupilIdFromToken(token) ?? '';
    final photo = await _store.readPhoto(pupilId);
    _prompt(_PendingScan(
      token: token,
      name: _store.nameForToken(token) ?? 'Pupil card',
      grade: _store.roster[pupilId]?['grade'] as String?,
      photo: photo,
      suggested: _store.suggestedTypeFor(pupilId, now),
      offline: true,
      when: now,
    ));
  }

  void _prompt(_PendingScan pending) {
    if (!mounted) return;
    _clearTimer?.cancel();
    // Always waits for a tap (arrived / leaving / cancel): nothing is recorded
    // on a timer, in staff mode or at a gate station.
    setState(() {
      _pending = pending;
      _feedback = null;
    });
  }

  void _cancelPending() {
    final pending = _pending;
    if (pending != null) _recentTokens.remove(pending.token);
    setState(() => _pending = null);
  }

  Future<void> _choose(String type) async {
    final pending = _pending;
    if (pending == null) return;
    setState(() => _pending = null);

    if (pending.offline) {
      await _saveOffline(pending, type);
      return;
    }
    try {
      final result = await widget.apiClient.pupilScan(pending.token, type: type);
      _sessionExpired = false;
      if (mounted) setState(() => _online = true);
      if (result['status'] == 'duplicate') {
        _show(_ScanFeedback(_Outcome.duplicate, pending.name,
            subtitle: pending.grade, note: 'Already recorded a moment ago', photo: pending.photo));
      } else {
        _show(_ScanFeedback(_Outcome.recorded, pending.name,
            subtitle: pending.grade, note: _typeLabel(type), photo: pending.photo));
      }
      unawaited(_syncQueue());
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        _sessionExpired = true;
        await _saveOffline(pending, type, reason: 'Sign in again to upload saved scans');
      } else if (e.statusCode == 402 || e.statusCode == 403) {
        _show(_ScanFeedback(_Outcome.blocked, 'Scanning unavailable', subtitle: _detail(e)));
      } else {
        _show(_ScanFeedback(_Outcome.rejected, 'Not recorded', subtitle: _detail(e)));
      }
    } catch (e) {
      if (_isNetworkError(e)) {
        if (mounted) setState(() => _online = false);
        await _saveOffline(pending, type);
      }
    }
  }

  Future<void> _saveOffline(_PendingScan pending, String type, {String? reason}) async {
    await _store.enqueue(pending.token, pending.when, type: type);
    _show(_ScanFeedback(
      _Outcome.saved,
      pending.name,
      photo: pending.photo,
      subtitle: pending.grade,
      note: '${_typeLabel(type)}\n${reason ?? 'No connection: saved on this device and will upload automatically'}',
    ));
  }

  void _show(_ScanFeedback feedback) {
    if (!mounted) return;
    _clearTimer?.cancel();
    setState(() => _feedback = feedback);
    _clearTimer = Timer(const Duration(seconds: 3), () {
      if (mounted) setState(() => _feedback = null);
    });
  }

  Future<void> _exitStation() async {
    final pinController = TextEditingController();
    bool wrong = false;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: const Text('Leave station mode?'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Enter the station PIN. Only the member of staff supervising the gate should leave this screen.'),
              TextField(
                controller: pinController,
                keyboardType: TextInputType.number,
                obscureText: true,
                maxLength: 4,
                autofocus: true,
                decoration: InputDecoration(labelText: 'PIN', counterText: '', errorText: wrong ? 'Wrong PIN' : null),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Stay')),
            TextButton(
              onPressed: () {
                if (pinController.text == _stationPin) {
                  Navigator.pop(ctx, true);
                } else {
                  pinController.clear();
                  setLocal(() => wrong = true);
                }
              },
              child: const Text('Leave'),
            ),
          ],
        ),
      ),
    );
    pinController.dispose();
    if (ok == true && mounted) {
      setState(() => _station = false);
      Navigator.of(context).pop();
    }
  }

  Future<void> _showRejected() async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Scans that could not be recorded'),
        content: SizedBox(
          width: double.maxFinite,
          child: ListView(
            shrinkWrap: true,
            children: [
              const Text('Please record these with the school office.', style: TextStyle(color: Colors.black54)),
              const SizedBox(height: 8),
              for (final r in _store.rejected)
                ListTile(
                  dense: true,
                  title: Text(r['name'] as String? ?? 'Unrecognised card'),
                  subtitle: Text('${_localTime(r['scanned_at'] as String)} - ${r['detail']}'),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () async {
              await _store.clearRejected();
              if (ctx.mounted) Navigator.pop(ctx);
              if (mounted) setState(() {});
            },
            child: const Text('Clear'),
          ),
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Close')),
        ],
      ),
    );
  }

  static String _localTime(String iso) {
    final t = DateTime.tryParse(iso)?.toLocal();
    if (t == null) return iso;
    final h = t.hour % 12 == 0 ? 12 : t.hour % 12;
    return '$h:${t.minute.toString().padLeft(2, '0')} ${t.hour >= 12 ? 'PM' : 'AM'}';
  }

  @override
  Widget build(BuildContext context) {
    final pending = _store.queue.length;
    return PopScope(
      canPop: !_station,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _station) _exitStation();
      },
      child: Scaffold(
        appBar: AppBar(
          automaticallyImplyLeading: !_station,
          title: Text(_station ? 'Gate Station' : 'Scan Pupil Cards'),
          actions: [
            if (_station)
              IconButton(
                tooltip: 'Leave station mode',
                icon: const Icon(Icons.lock),
                onPressed: _exitStation,
              )
            else
              IconButton(
                tooltip: 'Station mode',
                icon: const Icon(Icons.lock_outline),
                onPressed: () async {
                  if (await _ensurePin() && mounted) setState(() => _station = true);
                },
              ),
          ],
        ),
        body: Column(
          children: [
            _buildStatusBar(pending),
            Expanded(
              child: Stack(
                children: [
                  MobileScanner(onDetect: _handleDetection),
                  if (_feedback != null) Positioned.fill(child: _buildFeedback(_feedback!)),
                  if (_pending != null) Positioned.fill(child: _buildPending(_pending!)),
                ],
              ),
            ),
            if (!_station) _buildManualEntry(),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusBar(int pending) {
    final offline = !_online;
    final color = _sessionExpired
        ? Colors.orange.shade100
        : offline
            ? Colors.amber.shade100
            : Colors.green.shade50;
    final text = _sessionExpired
        ? 'Session expired - sign in again to upload $pending saved scan${pending == 1 ? '' : 's'}'
        : offline
            ? 'Offline - scans are saved on this device'
            : 'Online';
    return Material(
      color: color,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            Icon(offline || _sessionExpired ? Icons.cloud_off : Icons.cloud_done, size: 18),
            const SizedBox(width: 8),
            Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
            if (pending > 0) ...[
              Text('$pending waiting', style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              TextButton(
                onPressed: _syncing ? null : _syncQueue,
                child: Text(_syncing ? 'Syncing...' : 'Sync now'),
              ),
            ],
            if (_store.rejected.isNotEmpty)
              TextButton(
                onPressed: _showRejected,
                child: Text('${_store.rejected.length} need attention'),
              ),
          ],
        ),
      ),
    );
  }

  Widget _choiceButton(_PendingScan p, String type, IconData icon, Color color) {
    final suggested = p.suggested == type;
    final label = _typeLabel(type);
    final style = ButtonStyle(
      minimumSize: const WidgetStatePropertyAll(Size.fromHeight(64)),
      textStyle: const WidgetStatePropertyAll(TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
    );
    return suggested
        ? FilledButton.icon(
            style: style.copyWith(backgroundColor: WidgetStatePropertyAll(color)),
            onPressed: () => _choose(type),
            icon: Icon(icon),
            label: Text(label),
          )
        : OutlinedButton.icon(
            // Explicit colours: the app theme would otherwise paint every
            // button purple, which makes this one unreadable.
            style: style.copyWith(
              foregroundColor: WidgetStatePropertyAll(color),
              backgroundColor: const WidgetStatePropertyAll(Colors.white),
              side: WidgetStatePropertyAll(BorderSide(color: color, width: 2)),
            ),
            onPressed: () => _choose(type),
            icon: Icon(icon),
            label: Text(label),
          );
  }

  /// Shown right after a card is scanned: who it is, then the two options.
  Widget _buildPending(_PendingScan p) {
    return Container(
      color: Colors.white.withValues(alpha: 0.97),
      padding: const EdgeInsets.all(20),
      child: Center(
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: p.photo != null
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(16),
                        child: Image.memory(p.photo!, width: 150, height: 188, fit: BoxFit.cover, gaplessPlayback: true),
                      )
                    : const CircleAvatar(radius: 48, child: Icon(Icons.person, size: 56)),
              ),
              const SizedBox(height: 14),
              Text(p.name,
                  textAlign: TextAlign.center, style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
              if (p.grade != null && p.grade!.isNotEmpty)
                Text(p.grade!, textAlign: TextAlign.center, style: const TextStyle(fontSize: 18, color: Colors.black54)),
              if (p.lastNote != null)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(p.lastNote!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.black54)),
                ),
              if (p.offline)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text('No connection: this will be saved and uploaded automatically',
                      textAlign: TextAlign.center, style: TextStyle(color: Colors.amber.shade900)),
                ),
              const SizedBox(height: 18),
              _choiceButton(p, 'drop_off', Icons.login, Colors.green.shade700),
              const SizedBox(height: 12),
              _choiceButton(p, 'pick_up', Icons.logout, Colors.blue.shade700),
              const SizedBox(height: 8),
              TextButton(
                style: TextButton.styleFrom(
                  backgroundColor: Colors.transparent,
                  foregroundColor: Colors.black87,
                  minimumSize: const Size.fromHeight(44),
                ),
                onPressed: _cancelPending,
                child: const Text('Not this pupil / cancel'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFeedback(_ScanFeedback f) {
    final (Color bg, IconData icon) = switch (f.outcome) {
      _Outcome.recorded => (Colors.green.shade600, Icons.check_circle),
      _Outcome.saved => (Colors.amber.shade800, Icons.cloud_off),
      _Outcome.duplicate => (Colors.blueGrey.shade600, Icons.info),
      _Outcome.rejected => (Colors.red.shade600, Icons.cancel),
      _Outcome.blocked => (Colors.red.shade800, Icons.block),
    };
    return Container(
      color: bg.withValues(alpha: 0.94),
      padding: const EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (f.photo != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: Container(
                  decoration: BoxDecoration(border: Border.all(color: Colors.white, width: 4), borderRadius: BorderRadius.circular(16)),
                  child: Image.memory(f.photo!, width: 150, height: 188, fit: BoxFit.cover, gaplessPlayback: true),
                ),
              )
            else
              Icon(icon, color: Colors.white, size: 88),
            const SizedBox(height: 16),
            Text(
              f.title,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white, fontSize: 34, fontWeight: FontWeight.w700),
            ),
            if (f.subtitle != null) ...[
              const SizedBox(height: 6),
              Text(f.subtitle!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white, fontSize: 20)),
            ],
            if (f.note != null) ...[
              const SizedBox(height: 12),
              Text(f.note!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white, fontSize: 22)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildManualEntry() {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _manualTokenController,
              decoration: const InputDecoration(labelText: 'Camera not working? Enter card code', isDense: true),
              onChanged: (_) => setState(() {}),
            ),
          ),
          const SizedBox(width: 8),
          ElevatedButton(
            onPressed: _manualTokenController.text.trim().isEmpty
                ? null
                : () {
                    final token = _manualTokenController.text.trim();
                    _manualTokenController.clear();
                    _processToken(token);
                  },
            child: const Text('Record'),
          ),
        ],
      ),
    );
  }
}
