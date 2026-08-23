import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api_client.dart';
import 'link_guardian_screen.dart';

class SearchGuardiansScreen extends StatefulWidget {
  final ApiClient apiClient;
  const SearchGuardiansScreen({super.key, required this.apiClient});

  @override
  State<SearchGuardiansScreen> createState() => _SearchGuardiansScreenState();
}

class _SearchGuardiansScreenState extends State<SearchGuardiansScreen> {
  final _queryController = TextEditingController();
  List<Map<String, dynamic>>? _results;
  bool _loading = false;
  String? _error;
  String? _busyGuardianId;

  Future<void> _search() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await widget.apiClient.searchGuardians(_queryController.text.trim());
      setState(() => _results = results);
    } catch (e) {
      setState(() => _error = 'Search failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _printCredential(String guardianId, String guardianName) async {
    setState(() {
      _busyGuardianId = guardianId;
      _error = null;
    });
    try {
      final bytes = await widget.apiClient.downloadQrCredentialPdf(guardianId);
      final dir = await getTemporaryDirectory();
      final safeName = guardianName.replaceAll(RegExp(r'\s+'), '_');
      final file = File('${dir.path}/$safeName-qr-credential.pdf');
      await file.writeAsBytes(bytes, flush: true);
      await Share.shareXFiles([XFile(file.path)], subject: '$guardianName QR credential');
    } catch (e) {
      setState(() => _error = 'Could not get the QR credential: $e');
    } finally {
      if (mounted) setState(() => _busyGuardianId = null);
    }
  }

  Future<void> _resend(String guardianId) async {
    setState(() {
      _busyGuardianId = guardianId;
      _error = null;
    });
    try {
      await widget.apiClient.resendActivation(guardianId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Activation link resent.')));
      }
    } catch (e) {
      setState(() => _error = 'Resend failed: $e');
    } finally {
      if (mounted) setState(() => _busyGuardianId = null);
    }
  }

  @override
  void dispose() {
    _queryController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Search Guardians')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _queryController,
                    decoration: const InputDecoration(labelText: 'Name, email, or phone'),
                    onSubmitted: (_) => _search(),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _loading ? null : _search,
                  child: _loading
                      ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Search'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
            Expanded(
              child: _results == null
                  ? const Center(child: Text('Search for a guardian by name, email, or phone.'))
                  : _results!.isEmpty
                      ? const Center(child: Text('No guardians matched.'))
                      : ListView.builder(
                          itemCount: _results!.length,
                          itemBuilder: (context, index) {
                            final guardian = _results![index];
                            final id = guardian['id'] as String;
                            final name = guardian['name'] as String;
                            final busy = _busyGuardianId == id;
                            return Card(
                              child: Padding(
                                padding: const EdgeInsets.all(12),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(name, style: const TextStyle(fontWeight: FontWeight.w600)),
                                    if (guardian['email'] != null) Text(guardian['email'] as String),
                                    if (guardian['phone'] != null) Text(guardian['phone'] as String),
                                    const SizedBox(height: 8),
                                    Wrap(
                                      spacing: 8,
                                      runSpacing: 8,
                                      children: [
                                        ElevatedButton.icon(
                                          icon: const Icon(Icons.print, size: 18),
                                          label: const Text('Print QR'),
                                          onPressed: busy ? null : () => _printCredential(id, name),
                                        ),
                                        OutlinedButton.icon(
                                          icon: const Icon(Icons.mail_outline, size: 18),
                                          label: const Text('Resend activation'),
                                          onPressed: busy ? null : () => _resend(id),
                                        ),
                                        OutlinedButton.icon(
                                          icon: const Icon(Icons.link, size: 18),
                                          label: const Text('Link to another student'),
                                          onPressed: busy
                                              ? null
                                              : () => Navigator.of(context).push(
                                                    MaterialPageRoute(
                                                      builder: (_) => LinkGuardianScreen(
                                                        apiClient: widget.apiClient,
                                                        guardianId: id,
                                                        guardianName: name,
                                                      ),
                                                    ),
                                                  ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
    );
  }
}
