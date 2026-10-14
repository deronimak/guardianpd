import 'dart:async';
import 'dart:convert';

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
  const _ScanFeedback(this.outcome, this.title, {this.subtitle, this.note});
}

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
  Timer? _clearTimer;
  Timer? _syncTimer;
  bool _syncing = false;
  bool _ready = false;
  bool _online = true;
  bool _sessionExpired = false;

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
    } catch (e) {
      if (e is ApiException && e.statusCode == 401) _sessionExpired = true;
    }
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
    if (!_ready || capture.barcodes.isEmpty) return;
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
      final result = await widget.apiClient.pupilScan(token);
      _sessionExpired = false;
      final name = result['student_name'] as String? ?? 'Pupil';
      final grade = result['grade'] as String?;
      if (mounted) setState(() => _online = true);
      if (result['status'] == 'duplicate') {
        _show(_ScanFeedback(_Outcome.duplicate, name, subtitle: grade, note: 'Already scanned a moment ago'));
      } else {
        final arriving = result['type'] == 'drop_off';
        _show(_ScanFeedback(
          _Outcome.recorded,
          name,
          subtitle: grade,
          note: arriving ? 'Arrived at school' : 'Leaving school',
        ));
      }
      unawaited(_syncQueue());
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        // Login expired: don't lose the scan. Save it, and say what to do.
        _sessionExpired = true;
        await _saveOffline(token, now, reason: 'Sign in again to upload saved scans');
      } else if (e.statusCode == 402 || e.statusCode == 403) {
        _show(_ScanFeedback(_Outcome.blocked, 'Scanning unavailable', subtitle: _detail(e)));
      } else {
        _show(_ScanFeedback(_Outcome.rejected, 'Card not accepted', subtitle: _detail(e)));
      }
    } catch (e) {
      if (_isNetworkError(e)) {
        if (mounted) setState(() => _online = false);
        await _saveOffline(token, now);
      }
    }
  }

  Future<void> _saveOffline(String token, DateTime when, {String? reason}) async {
    await _store.enqueue(token, when);
    final name = _store.nameForToken(token);
    _show(_ScanFeedback(
      _Outcome.saved,
      name ?? 'Card saved',
      subtitle: _store.roster[OfflineScanStore.pupilIdFromToken(token)]?['grade'] as String?,
      note: reason ?? 'No connection: saved on this device and will upload automatically',
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
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Leave station mode?'),
        content: const Text('Only do this if you are the member of staff supervising the gate.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Stay')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Leave')),
        ],
      ),
    );
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
                onPressed: () => setState(() => _station = true),
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
