import 'package:flutter/material.dart';

import '../../core/api_client.dart';

class LinkGuardianScreen extends StatefulWidget {
  final ApiClient apiClient;
  final String guardianId;
  final String guardianName;

  const LinkGuardianScreen({
    super.key,
    required this.apiClient,
    required this.guardianId,
    required this.guardianName,
  });

  @override
  State<LinkGuardianScreen> createState() => _LinkGuardianScreenState();
}

class _LinkGuardianScreenState extends State<LinkGuardianScreen> {
  List<Map<String, dynamic>>? _students;
  String? _loadError;

  bool _showNewStudentForm = false;
  final _newStudentNameController = TextEditingController();
  final _newStudentGradeController = TextEditingController();

  String? _linkingStudentId;
  String? _error;
  String? _linkedMessage;

  @override
  void initState() {
    super.initState();
    _loadStudents();
  }

  Future<void> _loadStudents() async {
    setState(() => _loadError = null);
    try {
      final students = await widget.apiClient.listStudents();
      setState(() => _students = students);
    } catch (e) {
      setState(() => _loadError = 'Could not load students: $e');
    }
  }

  Future<void> _link(String studentId, String studentName) async {
    setState(() {
      _linkingStudentId = studentId;
      _error = null;
      _linkedMessage = null;
    });
    try {
      await widget.apiClient.linkGuardianToStudent(
        studentId: studentId,
        guardianId: widget.guardianId,
      );
      setState(() => _linkedMessage = '${widget.guardianName} is now linked to $studentName.');
    } catch (e) {
      setState(() => _error = 'Link failed: $e');
    } finally {
      if (mounted) setState(() => _linkingStudentId = null);
    }
  }

  Future<void> _createAndLink() async {
    final name = _newStudentNameController.text.trim();
    if (name.isEmpty) {
      setState(() => _error = "Enter the student's name");
      return;
    }
    setState(() {
      _linkingStudentId = 'new';
      _error = null;
      _linkedMessage = null;
    });
    try {
      final student = await widget.apiClient.createStudent(
        name: name,
        grade: _newStudentGradeController.text.trim(),
      );
      await widget.apiClient.linkGuardianToStudent(
        studentId: student['id'] as String,
        guardianId: widget.guardianId,
      );
      _newStudentNameController.clear();
      _newStudentGradeController.clear();
      setState(() {
        _linkedMessage = '${widget.guardianName} is now linked to ${student['name']}.';
        _showNewStudentForm = false;
      });
      _loadStudents();
    } catch (e) {
      setState(() => _error = 'Could not create student: $e');
    } finally {
      if (mounted) setState(() => _linkingStudentId = null);
    }
  }

  @override
  void dispose() {
    _newStudentNameController.dispose();
    _newStudentGradeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Link ${widget.guardianName}')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loadError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_loadError!, style: const TextStyle(color: Colors.red), textAlign: TextAlign.center),
              const SizedBox(height: 12),
              ElevatedButton(onPressed: _loadStudents, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    if (_students == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_linkedMessage != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(_linkedMessage!, style: const TextStyle(color: Colors.green)),
          ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text(_error!, style: const TextStyle(color: Colors.red)),
          ),
        Text('Existing students', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (_students!.isEmpty) const Text('No students yet — add one below.', style: TextStyle(color: Colors.black54)),
        for (final student in _students!)
          Card(
            child: ListTile(
              title: Text(student['name'] as String),
              subtitle: student['grade'] != null ? Text('Grade ${student['grade']}') : null,
              trailing: ElevatedButton(
                onPressed: _linkingStudentId != null
                    ? null
                    : () => _link(student['id'] as String, student['name'] as String),
                child: _linkingStudentId == student['id']
                    ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Link'),
              ),
            ),
          ),
        const SizedBox(height: 16),
        if (!_showNewStudentForm)
          OutlinedButton.icon(
            icon: const Icon(Icons.add),
            label: const Text('Add a new student'),
            onPressed: () => setState(() => _showNewStudentForm = true),
          )
        else
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _newStudentNameController,
                    decoration: const InputDecoration(labelText: "Student's full name"),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _newStudentGradeController,
                    decoration: const InputDecoration(labelText: 'Grade (optional)'),
                  ),
                  const SizedBox(height: 12),
                  ElevatedButton(
                    onPressed: _linkingStudentId != null ? null : _createAndLink,
                    child: _linkingStudentId == 'new'
                        ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Text('Create & link'),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}
