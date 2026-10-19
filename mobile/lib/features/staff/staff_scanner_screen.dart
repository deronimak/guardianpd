import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api_client.dart';
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

  late bool _station = widget.station;
  String? _stationPin;
  // The front camera works like a mirror, so people can see where to hold
  // their card; staff scanning with their own phone use the back camera.
  late final MobileScannerController _camera =
      MobileScannerController(facing: widget.station ? CameraFacing.front : CameraFacing.back);

  @override
  void initState() {
    super.initState();
    if (_station) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!await _ensurePin() && mounted) Navigator.of(context).pop();
      });
    }
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
    });
    try {
      final result = await widget.apiClient.lookupGuardianByQr(qrToken);
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
    } catch (e) {
      setState(() => _status = 'Lookup failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _recordAll() async {
    setState(() => _busy = true);
    final recorded = <String>[];
    final failed = <String>[];
    for (final student in _students!) {
      try {
        final result = await widget.apiClient.scanQr(
          qrToken: _pendingQrToken!,
          studentId: student['id'] as String,
          type: _type,
        );
        recorded.add('${student['name']} (${result['status']})');
      } catch (e) {
        failed.add(student['name'] as String);
      }
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _status = failed.isEmpty
          ? 'Recorded: ${recorded.join(', ')}'
          : 'Recorded ${recorded.length}, failed: ${failed.join(', ')}';
      _pendingQrToken = null;
      _guardianId = null;
      _guardianName = null;
      _feesOutstanding = false;
      _students = null;
    });
  }

  Future<void> _recordFor(String studentId, String studentName) async {
    setState(() => _busy = true);
    try {
      final result = await widget.apiClient.scanQr(
        qrToken: _pendingQrToken!,
        studentId: studentId,
        type: _type,
      );
      setState(() => _status = 'Recorded: ${result['status']} for $studentName');
    } catch (e) {
      setState(() => _status = 'Scan failed: $e');
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _pendingQrToken = null;
          _guardianId = null;
          _guardianName = null;
          _feesOutstanding = false;
          _students = null;
        });
      }
    }
  }

  @override
  void dispose() {
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
