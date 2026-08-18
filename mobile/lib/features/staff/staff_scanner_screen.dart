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
  String _status = "Point the camera at a guardian's QR code";
  bool _busy = false;

  Future<void> _handleDetection(BarcodeCapture capture) async {
    if (_busy || capture.barcodes.isEmpty) return;
    final rawValue = capture.barcodes.first.rawValue;
    if (rawValue == null) return;

    setState(() {
      _busy = true;
      _status = 'Scanning...';
    });

    // NOTE: student_id and type are hardcoded placeholders. A real screen
    // needs the staff member to pick which child and drop-off vs. pick-up
    // around the scan — see ARCHITECTURE.md §6. Not yet built.
    try {
      final result = await widget.apiClient.scanQr(
        qrToken: rawValue,
        studentId: '00000000-0000-0000-0000-000000000000',
        type: 'drop_off',
      );
      setState(() => _status = 'Recorded: ${result['status']}');
    } catch (e) {
      setState(() => _status = 'Scan failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan Guardian QR')),
      body: Column(
        children: [
          Expanded(child: MobileScanner(onDetect: _handleDetection)),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(_status, textAlign: TextAlign.center),
          ),
        ],
      ),
    );
  }
}
