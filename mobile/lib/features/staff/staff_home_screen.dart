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
              Container(
                width: 56,
                height: 56,
                margin: const EdgeInsets.only(bottom: 24),
                alignment: Alignment.center,
                decoration: const BoxDecoration(color: Color(0xFF6A4FE0), shape: BoxShape.circle),
                child: const Icon(Icons.qr_code_scanner, color: Colors.white, size: 26),
              ),
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
