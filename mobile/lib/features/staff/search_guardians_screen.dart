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
  String? _busyId;

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
      _busyId = guardianId;
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
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _resend(String guardianId) async {
    setState(() {
      _busyId = guardianId;
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
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _editGuardian(Map<String, dynamic> guardian) async {
    final nameController = TextEditingController(text: guardian['name'] as String? ?? '');
    final emailController = TextEditingController(text: guardian['email'] as String? ?? '');
    final phoneController = TextEditingController(text: guardian['phone'] as String? ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Edit guardian'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: nameController, decoration: const InputDecoration(labelText: 'Name')),
            TextField(controller: emailController, decoration: const InputDecoration(labelText: 'Email')),
            TextField(controller: phoneController, decoration: const InputDecoration(labelText: 'Phone')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save')),
        ],
      ),
    );
    if (saved != true) return;

    final id = guardian['id'] as String;
    setState(() {
      _busyId = id;
      _error = null;
    });
    try {
      await widget.apiClient.updateGuardian(
        id,
        name: nameController.text.trim(),
        email: emailController.text.trim(),
        phone: phoneController.text.trim(),
      );
      await _search();
    } catch (e) {
      setState(() => _error = 'Update failed: $e');
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _deleteGuardian(String guardianId, String name) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Delete guardian?'),
        content: Text(
          'Permanently delete $name? This also removes their QR credential and attendance history. This cannot be undone.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _busyId = guardianId;
      _error = null;
    });
    try {
      await widget.apiClient.deleteGuardian(guardianId);
      await _search();
    } catch (e) {
      setState(() => _error = 'Delete failed: $e');
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _editChild(Map<String, dynamic> child) async {
    final nameController = TextEditingController(text: child['name'] as String? ?? '');
    final gradeController = TextEditingController(text: child['grade'] as String? ?? '');
    final saved = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Edit child'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: nameController, decoration: const InputDecoration(labelText: 'Name')),
            TextField(controller: gradeController, decoration: const InputDecoration(labelText: 'Grade')),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Save')),
        ],
      ),
    );
    if (saved != true) return;

    final id = child['id'] as String;
    setState(() {
      _busyId = id;
      _error = null;
    });
    try {
      await widget.apiClient.updateStudent(id, name: nameController.text.trim(), grade: gradeController.text.trim());
      await _search();
    } catch (e) {
      setState(() => _error = 'Update failed: $e');
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _deleteChild(String studentId, String name) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Delete child?'),
        content: Text('Permanently delete $name? This also removes their attendance history. This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(dialogContext, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _busyId = studentId;
      _error = null;
    });
    try {
      await widget.apiClient.deleteStudent(studentId);
      await _search();
    } catch (e) {
      setState(() => _error = 'Delete failed: $e');
    } finally {
      if (mounted) setState(() => _busyId = null);
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
                          itemBuilder: (context, index) => _guardianCard(_results![index]),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _guardianCard(Map<String, dynamic> guardian) {
    final id = guardian['id'] as String;
    final name = guardian['name'] as String;
    final busy = _busyId == id;
    final children = (guardian['children'] as List? ?? []).cast<Map<String, dynamic>>();

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
                OutlinedButton.icon(
                  icon: const Icon(Icons.edit, size: 18),
                  label: const Text('Edit'),
                  onPressed: busy ? null : () => _editGuardian(guardian),
                ),
                OutlinedButton.icon(
                  icon: const Icon(Icons.delete_outline, size: 18),
                  label: const Text('Delete'),
                  onPressed: busy ? null : () => _deleteGuardian(id, name),
                ),
              ],
            ),
            if (children.isNotEmpty) ...[
              const Divider(height: 20),
              const Text('Children', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
              for (final child in children) _childRow(child),
            ],
          ],
        ),
      ),
    );
  }

  Widget _childRow(Map<String, dynamic> child) {
    final studentId = child['id'] as String;
    final name = child['name'] as String;
    final grade = child['grade'] as String?;
    final busy = _busyId == studentId;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(child: Text(grade != null && grade.isNotEmpty ? '$name · $grade' : name)),
          IconButton(
            icon: const Icon(Icons.edit, size: 18),
            onPressed: busy ? null : () => _editChild(child),
            tooltip: 'Edit',
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline, size: 18),
            onPressed: busy ? null : () => _deleteChild(studentId, name),
            tooltip: 'Delete',
          ),
        ],
      ),
    );
  }
}
