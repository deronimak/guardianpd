import 'package:flutter/material.dart';

import '../../core/parent_api_client.dart';
import 'parent_home_screen.dart';

class ParentActivateScreen extends StatefulWidget {
  const ParentActivateScreen({super.key});

  @override
  State<ParentActivateScreen> createState() => _ParentActivateScreenState();
}

class _ParentActivateScreenState extends State<ParentActivateScreen> {
  final _emailController = TextEditingController();
  final _codeController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _loading = false;
  String? _error;

  Future<void> _activate() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final client = ParentApiClient();
    try {
      await client.activate(
        email: _emailController.text.trim(),
        inviteToken: _codeController.text.trim(),
        password: _passwordController.text,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => ParentHomeScreen(apiClient: client)),
      );
    } catch (e) {
      setState(() => _error = 'Activation failed: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _codeController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Activate Your Account')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const Text('Enter the activation code the school emailed you, and choose a password.'),
            const SizedBox(height: 16),
            TextField(
              controller: _emailController,
              decoration: const InputDecoration(labelText: 'Email'),
            ),
            TextField(
              controller: _codeController,
              decoration: const InputDecoration(labelText: 'Activation code'),
            ),
            TextField(
              controller: _passwordController,
              decoration: const InputDecoration(labelText: 'New password'),
              obscureText: true,
            ),
            const SizedBox(height: 16),
            if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loading ? null : _activate,
              child: _loading ? const CircularProgressIndicator() : const Text('Activate'),
            ),
          ],
        ),
      ),
    );
  }
}
