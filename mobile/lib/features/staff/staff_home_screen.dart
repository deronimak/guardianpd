import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/offline_scan_store.dart';
import 'pupil_scanner_screen.dart';
import 'staff_scanner_screen.dart';

class StaffHomeScreen extends StatefulWidget {
  final ApiClient apiClient;
  const StaffHomeScreen({super.key, required this.apiClient});

  @override
  State<StaffHomeScreen> createState() => _StaffHomeScreenState();
}

class _StaffHomeScreenState extends State<StaffHomeScreen> {
  late final OfflineScanStore _store = OfflineScanStore.forSchool(widget.apiClient.schoolSlug);
  // The school's mode decides which scanner is offered. Remembered on the
  // device so a staff member who opens the app with no signal at the gate
  // still gets the right screen.
  String _mode = 'guardian';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadMode();
  }

  Future<void> _loadMode() async {
    await _store.load();
    if (_store.credentialMode != null) {
      _mode = _store.credentialMode!;
    }
    if (mounted) setState(() => _loading = _store.credentialMode == null);
    try {
      final profile = await widget.apiClient.getSchoolProfile();
      final mode = profile['credential_mode'] as String? ?? 'guardian';
      await _store.setCredentialMode(mode);
      _mode = mode;
    } catch (_) {
      // Offline or error: keep the remembered (or default) mode.
    }
    if (mounted) setState(() => _loading = false);
  }

  void _open(Widget screen) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen)).then((_) {
      if (mounted) setState(() {});
    });
  }

  @override
  Widget build(BuildContext context) {
    final pupilMode = _mode == 'pupil';
    final pending = _store.queue.length;
    return Scaffold(
      appBar: AppBar(title: const Text('School Staff')),
      body: Center(
        child: _loading
            ? const CircularProgressIndicator()
            : Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      margin: const EdgeInsets.only(bottom: 24),
                      alignment: Alignment.center,
                      decoration: const BoxDecoration(color: Color(0xFF6A4FE0), shape: BoxShape.circle),
                      child: const Icon(Icons.qr_code_scanner, color: Colors.white, size: 26),
                    ),
                    if (pupilMode) ...[
                      ElevatedButton.icon(
                        icon: const Icon(Icons.qr_code_scanner),
                        label: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: Text('Scan Pupil Cards'),
                        ),
                        onPressed: () => _open(PupilScannerScreen(apiClient: widget.apiClient)),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.lock_outline),
                        label: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: Text('Gate Station Mode'),
                        ),
                        onPressed: () => _open(PupilScannerScreen(apiClient: widget.apiClient, station: true)),
                      ),
                      if (pending > 0) ...[
                        const SizedBox(height: 16),
                        Text(
                          '$pending scan${pending == 1 ? '' : 's'} saved offline, waiting to upload',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.amber.shade900),
                        ),
                      ],
                    ] else
                      ElevatedButton.icon(
                        icon: const Icon(Icons.qr_code_scanner),
                        label: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: Text('Scan Guardian QR'),
                        ),
                        onPressed: () => _open(StaffScannerScreen(apiClient: widget.apiClient)),
                      ),
                    if (!pupilMode) ...[
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        icon: const Icon(Icons.lock_outline),
                        label: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: Text('Gate Station Mode'),
                        ),
                        onPressed: () => _open(StaffScannerScreen(apiClient: widget.apiClient, station: true)),
                      ),
                    ],
                  ],
                ),
              ),
      ),
    );
  }
}
