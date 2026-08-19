import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api_client.dart';

class StaffScannerScreen extends StatefulWidget {
  final ApiClient apiClient;
  const StaffScannerScreen({super.key, required this.apiClient});

  @override
  State<StaffScannerScreen> createState() => _StaffScannerScreenState();
}

class _StaffScannerScreenState extends State<StaffScannerScreen> {
  final _manualTokenController = TextEditingController();

  bool _busy = false;
  String _status = "Point the camera at a guardian's QR code";

  // Populated once a scanned/entered code resolves to a guardian.
  String? _pendingQrToken;
  String? _guardianId;
  String? _guardianName;
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
      _students = null;
    });
    try {
      final result = await widget.apiClient.lookupGuardianByQr(qrToken);
      final students = (result['students'] as List).cast<Map<String, dynamic>>();
      setState(() {
        _pendingQrToken = qrToken;
        _guardianId = result['guardian_id'] as String;
        _guardianName = result['guardian_name'] as String;
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
          _students = null;
        });
      }
    }
  }

  @override
  void dispose() {
    _manualTokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Guardian QR')),
      body: Column(
        children: [
          Expanded(
            flex: _guardianId == null ? 3 : 1,
            child: MobileScanner(onDetect: _handleDetection),
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
    );
  }

  Widget _buildIdleControls() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(_status, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        const Text('Camera not working? Enter the code manually:', style: TextStyle(color: Colors.black54)),
        const SizedBox(height: 8),
        TextField(
          controller: _manualTokenController,
          decoration: const InputDecoration(labelText: 'QR token', border: OutlineInputBorder()),
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
    );
  }

  Widget _buildPicker() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(_guardianName!, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
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
            _students = null;
            _status = "Point the camera at a guardian's QR code";
          }),
          child: const Text('Cancel'),
        ),
      ],
    );
  }
}
