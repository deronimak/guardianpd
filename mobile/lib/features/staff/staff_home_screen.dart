import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import 'staff_scanner_screen.dart';

class StaffHomeScreen extends StatelessWidget {
  final ApiClient apiClient;
  const StaffHomeScreen({super.key, required this.apiClient});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('School Staff')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ElevatedButton.icon(
                icon: const Icon(Icons.qr_code_scanner),
                label: const Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: Text('Scan Guardian QR'),
                ),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => StaffScannerScreen(apiClient: apiClient)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
