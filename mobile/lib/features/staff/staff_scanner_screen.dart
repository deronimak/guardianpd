import 'dart:async';

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api_client.dart';
import '../../core/offline_scan_store.dart';
import 'station_lock.dart';

class StaffScannerScreen extends StatefulWidget {
  final ApiClient apiClient;
  // Gate station: locked behind a PIN, front camera, supervised by staff.
  final bool station;
  const StaffScannerScreen({super.key, required this.apiClient, this.station = false});

  @override
  State<StaffScannerScreen> createState() => _StaffScannerScreenState();
}

class _StaffScannerScreenState extends State<StaffScannerScreen> {
  final _manualTokenController = TextEditingController();

  // Offline support: a cached list of guardians and their children, and scans
  // saved on the phone when there is no signal, uploaded automatically later.
  late final OfflineScanStore _store = OfflineScanStore.forSchool(widget.apiClient.schoolSlug);
  Timer? _syncTimer;
  bool _syncing = false;
  bool _online = true;
  bool _sessionExpired = false;
  // The guardian on screen was identified from the saved list (no signal).
  bool _offlineLookup = false;

  late bool _station = widget.station;
  String? _stationPin;
  // The front camera works like a mirror, so people can see where to hold
  // their card; staff scanning with their own phone use the back camera.
  late final MobileScannerController _camera =
      MobileScannerController(facing: widget.station ? CameraFacing.front : CameraFacing.back);

  @override
  void initState() {
    super.initState();
    _initOffline();
    if (_station) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!await _ensurePin() && mounted) Navigator.of(context).pop();
      });
    }
  }

  Future<void> _initOffline() async {
    await _store.load();
    if (mounted) setState(() {});
    unawaited(_refreshRoster());
    unawaited(_syncQueue());
    _syncTimer = Timer.periodic(const Duration(seconds: 30), (_) => _syncQueue());
  }

  Future<void> _refreshRoster() async {
    try {
      await _store.setGuardianRoster(await widget.apiClient.guardianScanRoster());
      if (mounted) setState(() => _online = true);
    } on ApiException catch (e) {
      if (e.statusCode == 401) _sessionExpired = true;
    } catch (_) {
      if (mounted) setState(() => _online = false);
    }
  }

  Future<void> _syncQueue() async {
    if (_syncing || _store.guardianQueue.isEmpty) return;
    _syncing = true;
    if (mounted) setState(() {});
    try {
      final sent = List<Map<String, dynamic>>.from(_store.guardianQueue);
      final results = await widget.apiClient.scanBatch([
        for (final item in sent)
          {
            'token': item['token'],
            'student_id': item['student_id'],
            'type': item['type'],
            'scanned_at': item['scanned_at'],
          },
      ]);
      await _store.applyGuardianBatchResults(sent, results);
      _sessionExpired = false;
      if (mounted) setState(() => _online = true);
      unawaited(_refreshRoster());
    } on ApiException catch (e) {
      if (e.statusCode == 401) _sessionExpired = true;
      // Other answers (e.g. subscription inactive): keep the saved scans.
    } catch (_) {
      if (mounted) setState(() => _online = false);
    } finally {
      _syncing = false;
      if (mounted) setState(() {});
    }
  }

  Future<void> _showRejected() async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Scans that need attention'),
        content: SizedBox(
          width: double.maxFinite,
          child: ListView(
            shrinkWrap: true,
            children: [
              const Text('These saved scans could not be recorded. Please check them with the school office.',
                  style: TextStyle(color: Colors.black54)),
              const SizedBox(height: 8),
              for (final r in _store.rejected)
                ListTile(
                  dense: true,
                  title: Text(r['name'] as String? ?? 'Unknown'),
                  subtitle: Text('${r['scanned_at']} - ${r['detail']}'),
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

  Widget _buildStatusBar() {
    final pending = _store.guardianQueue.length;
    final offline = !_online;
    final color = _sessionExpired
        ? Colors.orange.shade100
        : offline
            ? Colors.amber.shade100
            : Colors.green.shade50;
    final text = _sessionExpired
        ? 'Session expired - sign in again to upload saved scans'
        : offline
            ? 'Offline - scans are saved on this phone'
            : 'Online';
    return Material(
      color: color,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
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
              TextButton(onPressed: _showRejected, child: Text('${_store.rejected.length} need attention')),
          ],
        ),
      ),
    );
  }

  Future<bool> _ensurePin() async {
    if (_stationPin != null) return true;
    final pin = await promptSetStationPin(context);
    if (pin == null) return false;
    _stationPin = pin;
    return true;
  }

  Future<void> _exitStation() async {
    if (await confirmLeaveStation(context, _stationPin) && mounted) {
      setState(() => _station = false);
      Navigator.of(context).pop();
    }
  }

  bool _busy = false;
  String _status = "Point the camera at a guardian's QR code";

  // Populated once a scanned/entered code resolves to a guardian.
  String? _pendingQrToken;
  String? _guardianId;
  String? _guardianName;
  // School Admin-set visibility flag (see backend's GuardianLookupOut) —
  // shown to staff here so they can act on it in person, never used to
  // disable Record/Record all below.
  bool _feesOutstanding = false;
  List<Map<String, dynamic>>? _students;
  String _type = 'drop_off';

  Future<void> _handleDetection(BarcodeCapture capture) async {
    if (_busy || capture.barcodes.isEmpty) return;
    final rawValue = capture.barcodes.first.rawValue;
    if (rawValue == null) return;
    await _lookup(rawValue);
  }

  Future<void> _lookup(String qrToken) async {
    setState(() {
      _busy = true;
      _status = 'Looking up guardian...';
      _guardianId = null;
      _guardianName = null;
      _feesOutstanding = false;
      _students = null;
      _offlineLookup = false;
    });
    try {
      final result = await widget.apiClient.lookupGuardianByQr(qrToken);
      if (mounted) setState(() => _online = true);
      final students = (result['students'] as List).cast<Map<String, dynamic>>();
      setState(() {
        _pendingQrToken = qrToken;
        _guardianId = result['guardian_id'] as String;
        _guardianName = result['guardian_name'] as String;
        _feesOutstanding = result['fees_outstanding'] as bool? ?? false;
        _students = students;
        _status = students.isEmpty
            ? '${result['guardian_name']} is not authorized for any student here'
            : 'Select drop-off or pick-up, then the child';
      });
      _manualTokenController.clear();
    } on ApiException catch (e) {
      if (e.statusCode == 401) {
        _sessionExpired = true;
        _lookupOffline(qrToken);
      } else {
        setState(() => _status = 'Lookup failed: $e');
      }
    } catch (_) {
      // No signal (or a timeout): identify the card from the saved list.
      if (mounted) setState(() => _online = false);
      _lookupOffline(qrToken);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _lookupOffline(String qrToken) {
    final gid = OfflineScanStore.guardianIdFromToken(qrToken);
    final entry = gid == null ? null : _store.guardianRoster[gid];
    if (entry == null) {
      setState(() => _status = 'No connection, and this card is not in the saved list. Try again when online.');
      return;
    }
    final students = (entry['students'] as List).cast<Map<String, dynamic>>();
    setState(() {
      _offlineLookup = true;
      _pendingQrToken = qrToken;
      _guardianId = entry['guardian_id'] as String;
      _guardianName = entry['guardian_name'] as String;
      _feesOutstanding = entry['fees_outstanding'] as bool? ?? false;
      _students = students;
      _status = students.isEmpty
          ? '${entry['guardian_name']} is not authorized for any student here'
          : 'No connection: choose drop-off or pick-up, then the child. It will be saved and uploaded automatically.';
    });
  }

  /// Records one child: live if possible, otherwise saved on the phone for
  /// upload later. Returns the server's status ("recorded"/"duplicate"), or
  /// "saved" when it was kept for later.
  Future<String> _recordStudent(Map<String, dynamic> student) async {
    final token = _pendingQrToken!;
    final id = student['id'] as String;
    if (!_offlineLookup) {
      try {
        final result = await widget.apiClient.scanQr(qrToken: token, studentId: id, type: _type);
        if (mounted) setState(() => _online = true);
        return result['status'] as String? ?? 'recorded';
      } on ApiException catch (e) {
        if (e.statusCode != 401) rethrow;
        _sessionExpired = true;
      } catch (_) {
        if (mounted) setState(() => _online = false);
      }
    }
    await _store.enqueueGuardianScan(
      token: token,
      studentId: id,
      type: _type,
      scannedAt: DateTime.now(),
      guardianName: _guardianName,
      studentName: student['name'] as String?,
    );
    return 'saved';
  }

  Future<void> _recordAll() async {
    setState(() => _busy = true);
    final done = <String>[];
    final failed = <String>[];
    for (final student in _students!) {
      try {
        final outcome = await _recordStudent(student);
        done.add(outcome == 'saved' ? '${student['name']} (saved offline)' : '${student['name']} ($outcome)');
      } catch (e) {
        failed.add(student['name'] as String);
      }
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _status = failed.isEmpty
          ? 'Recorded: ${done.join(', ')}'
          : 'Recorded ${done.length}, failed: ${failed.join(', ')}';
      _clearGuardian();
    });
    unawaited(_syncQueue());
  }

  Future<void> _recordFor(String studentId, String studentName) async {
    setState(() => _busy = true);
    try {
      final student = _students!.firstWhere((s) => s['id'] == studentId);
      final outcome = await _recordStudent(student);
      setState(() => _status = outcome == 'saved'
          ? 'Saved on this phone for $studentName - it will upload automatically'
          : 'Recorded: $outcome for $studentName');
    } catch (e) {
      setState(() => _status = 'Scan failed: $e');
    } finally {
      if (mounted) {
        setState(_clearGuardian);
        unawaited(_syncQueue());
      }
    }
  }

  void _clearGuardian() {
    _busy = false;
    _pendingQrToken = null;
    _guardianId = null;
    _guardianName = null;
    _feesOutstanding = false;
    _students = null;
    _offlineLookup = false;
  }

  @override
  void dispose() {
    _syncTimer?.cancel();
    _camera.dispose();
    _manualTokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_station,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop && _station) _exitStation();
      },
      child: Scaffold(
        appBar: AppBar(
          automaticallyImplyLeading: !_station,
          title: Text(_station ? 'Gate Station' : 'Scan Guardian QR'),
          actions: [
            IconButton(
              tooltip: 'Switch camera',
              icon: const Icon(Icons.cameraswitch),
              onPressed: () => _camera.switchCamera(),
            ),
            if (_station)
              IconButton(tooltip: 'Leave station mode', icon: const Icon(Icons.lock), onPressed: _exitStation)
            else
              IconButton(
                tooltip: 'Station mode',
                icon: const Icon(Icons.lock_outline),
                onPressed: () async {
                  if (await _ensurePin() && mounted) {
                    setState(() => _station = true);
                    if (_camera.value.cameraDirection == CameraFacing.back) await _camera.switchCamera();
                  }
                },
              ),
          ],
        ),
        body: Column(
          children: [
            _buildStatusBar(),
            Expanded(
              flex: _guardianId == null ? 3 : 1,
              child: Stack(
                children: [
                  MobileScanner(controller: _camera, onDetect: _handleDetection),
                  if (_station && _guardianId == null)
                    const Positioned.fill(child: StationFrameGuide(message: 'Hold your QR card inside the box')),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              flex: 2,
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: _guardianId == null ? _buildIdleControls() : _buildPicker(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildIdleControls() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(_status, textAlign: TextAlign.center, style: _station ? const TextStyle(fontSize: 18) : null),
        if (!_station) ...[
        const SizedBox(height: 16),
        const Text('Camera not working? Enter the code manually:', style: TextStyle(color: Colors.black54)),
        const SizedBox(height: 8),
        TextField(
          controller: _manualTokenController,
          decoration: const InputDecoration(labelText: 'QR token'),
          maxLines: 2,
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: 8),
        ElevatedButton(
          onPressed: _busy || _manualTokenController.text.trim().isEmpty
              ? null
              : () => _lookup(_manualTokenController.text.trim()),
          child: const Text('Look up'),
        ),
        ],
      ],
    );
  }

  Widget _buildPicker() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Flexible(
              child: Text(_guardianName!, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            ),
            if (_feesOutstanding && _station)
              Padding(
                padding: const EdgeInsets.only(left: 8),
                child: Icon(Icons.flag, size: 18, color: Colors.amber.shade800),
              ),
            if (_feesOutstanding && !_station) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: Text(
                  'Fees outstanding',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.red.shade700),
                ),
              ),
            ],
          ],
        ),
        Text(_status, style: const TextStyle(color: Colors.black54)),
        const SizedBox(height: 12),
        SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'drop_off', label: Text('Drop-off')),
            ButtonSegment(value: 'pick_up', label: Text('Pick-up')),
          ],
          selected: {_type},
          onSelectionChanged: (selection) => setState(() => _type = selection.first),
        ),
        if (_students!.length > 1) ...[
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _busy ? null : _recordAll,
            child: Text('Record all ${_students!.length} children'),
          ),
        ],
        const SizedBox(height: 12),
        for (final student in _students!)
          Card(
            child: ListTile(
              title: Text(student['name'] as String),
              subtitle: student['grade'] != null ? Text('Grade ${student['grade']}') : null,
              trailing: ElevatedButton(
                onPressed: _busy ? null : () => _recordFor(student['id'] as String, student['name'] as String),
                child: const Text('Record'),
              ),
            ),
          ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: () => setState(() {
            _pendingQrToken = null;
            _guardianId = null;
            _guardianName = null;
            _feesOutstanding = false;
            _students = null;
            _status = "Point the camera at a guardian's QR code";
          }),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}
