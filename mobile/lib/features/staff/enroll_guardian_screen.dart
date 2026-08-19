import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/api_client.dart';

class EnrollGuardianScreen extends StatefulWidget {
  final ApiClient apiClient;
  const EnrollGuardianScreen({super.key, required this.apiClient});

  @override
  State<EnrollGuardianScreen> createState() => _EnrollGuardianScreenState();
}

class _EnrollGuardianScreenState extends State<EnrollGuardianScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();

  bool _submitting = false;
  bool _sharing = false;
  String? _error;

  // Set once enrollment succeeds; drives the success panel below the form.
  String? _enrolledGuardianId;
  String? _enrolledGuardianName;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final guardian = await widget.apiClient.createGuardian(
        name: _nameController.text.trim(),
        email: _emailController.text.trim(),
        phone: _phoneController.text.trim(),
      );
      setState(() {
        _enrolledGuardianId = guardian['id'] as String;
        _enrolledGuardianName = guardian['name'] as String;
      });
    } catch (e) {
      setState(() => _error = 'Enroll failed: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  Future<void> _shareCredential() async {
    setState(() {
      _sharing = true;
      _error = null;
    });
    try {
      final bytes = await widget.apiClient.downloadQrCredentialPdf(_enrolledGuardianId!);
      final dir = await getTemporaryDirectory();
      final safeName = _enrolledGuardianName!.replaceAll(RegExp(r'\s+'), '_');
      final file = File('${dir.path}/$safeName-qr-credential.pdf');
      await file.writeAsBytes(bytes, flush: true);
      await Share.shareXFiles([XFile(file.path)], subject: '$_enrolledGuardianName QR credential');
    } catch (e) {
      setState(() => _error = 'Could not get the QR credential: $e');
    } finally {
      if (mounted) setState(() => _sharing = false);
    }
  }

  void _enrollAnother() {
    _nameController.clear();
    _emailController.clear();
    _phoneController.clear();
    setState(() {
      _enrolledGuardianId = null;
      _enrolledGuardianName = null;
      _error = null;
    });
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final enrolled = _enrolledGuardianId != null;
    return Scaffold(
      appBar: AppBar(title: const Text('Enroll Guardian')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: enrolled ? _buildSuccessPanel() : _buildForm(),
      ),
    );
  }

  Widget _buildForm() {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextFormField(
            controller: _nameController,
            decoration: const InputDecoration(labelText: "Guardian's full name"),
            validator: (value) => (value == null || value.trim().isEmpty) ? 'Required' : null,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _emailController,
            decoration: const InputDecoration(labelText: 'Email'),
            keyboardType: TextInputType.emailAddress,
            validator: (value) =>
                (value == null || !value.contains('@')) ? 'Enter a valid email' : null,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _phoneController,
            decoration: const InputDecoration(labelText: 'Phone (optional)'),
            keyboardType: TextInputType.phone,
          ),
          const SizedBox(height: 24),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(_error!, style: const TextStyle(color: Colors.red)),
            ),
          ElevatedButton(
            onPressed: _submitting ? null : _submit,
            child: _submitting
                ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator())
                : const Text('Enroll guardian'),
          ),
        ],
      ),
    );
  }

  Widget _buildSuccessPanel() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Icon(Icons.check_circle, color: Colors.green.shade600, size: 48),
        const SizedBox(height: 12),
        Text(
          '$_enrolledGuardianName enrolled',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 4),
        const Text(
          "An activation email was sent (or logged, in dev). Their printed QR credential is ready below.",
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.black54),
        ),
        const SizedBox(height: 24),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Text(_error!, style: const TextStyle(color: Colors.red)),
          ),
        ElevatedButton.icon(
          onPressed: _sharing ? null : _shareCredential,
          icon: _sharing
              ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.print),
          label: const Text('Share / print QR credential'),
        ),
        const SizedBox(height: 12),
        OutlinedButton(
          onPressed: _enrollAnother,
          child: const Text('Enroll another guardian'),
        ),
      ],
    );
  }
}
