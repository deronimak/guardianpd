import 'package:flutter/material.dart';

import '../../core/api_client.dart';

class AddStaffScreen extends StatefulWidget {
  final ApiClient apiClient;
  const AddStaffScreen({super.key, required this.apiClient});

  @override
  State<AddStaffScreen> createState() => _AddStaffScreenState();
}

class _AddStaffScreenState extends State<AddStaffScreen> {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _submitting = false;
  String? _error;
  String? _successMessage;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
      _successMessage = null;
    });
    try {
      await widget.apiClient.createStaffAccount(
        username: _usernameController.text.trim(),
        password: _passwordController.text,
      );
      setState(() => _successMessage = 'Staff account "${_usernameController.text.trim()}" created.');
      _usernameController.clear();
      _passwordController.clear();
    } catch (e) {
      setState(() => _error = 'Could not create account: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Add Staff Account')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_successMessage != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Text(_successMessage!, style: const TextStyle(color: Colors.green)),
                ),
              TextFormField(
                controller: _usernameController,
                decoration: const InputDecoration(labelText: 'Username'),
                validator: (value) => (value == null || value.trim().length < 3) ? 'Min 3 characters' : null,
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _passwordController,
                decoration: const InputDecoration(labelText: 'Password'),
                obscureText: true,
                validator: (value) => (value == null || value.length < 8) ? 'Min 8 characters' : null,
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
                    : const Text('Create staff account'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
