import 'package:flutter/material.dart';

import '../../core/parent_api_client.dart';

/// Attendance history + planned-absence marking for one child
/// (ARCHITECTURE.md §7/§8) — reached by tapping a child in My Children.
class StudentDetailScreen extends StatefulWidget {
  final ParentApiClient apiClient;
  final String schoolSlug;
  final String studentId;
  final String studentName;

  const StudentDetailScreen({
    super.key,
    required this.apiClient,
    required this.schoolSlug,
    required this.studentId,
    required this.studentName,
  });

  @override
  State<StudentDetailScreen> createState() => _StudentDetailScreenState();
}

class _StudentDetailScreenState extends State<StudentDetailScreen> {
  late Future<List<Map<String, dynamic>>> _historyFuture;
  late Future<List<Map<String, dynamic>>> _absencesFuture;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  void _reload() {
    _historyFuture = widget.apiClient.attendanceHistory(
      schoolSlug: widget.schoolSlug,
      studentId: widget.studentId,
    );
    _absencesFuture = widget.apiClient.expectedAbsences(
      schoolSlug: widget.schoolSlug,
      studentId: widget.studentId,
    );
  }

  Future<void> _openMarkAbsenceDialog() async {
    final created = await showDialog<bool>(
      context: context,
      builder: (_) => _MarkAbsenceDialog(
        apiClient: widget.apiClient,
        schoolSlug: widget.schoolSlug,
        studentId: widget.studentId,
      ),
    );
    if (created == true && mounted) {
      setState(_reload);
    }
  }

  String _formatEventType(String type) => type == 'drop_off' ? 'Dropped off' : 'Picked up';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.studentName)),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openMarkAbsenceDialog,
        icon: const Icon(Icons.event_busy),
        label: const Text('Mark absence'),
      ),
      body: RefreshIndicator(
        onRefresh: () async => setState(_reload),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Planned absences', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 8),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: _absencesFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 16),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snapshot.hasError) {
                  return Text('Failed to load: ${snapshot.error}');
                }
                final absences = snapshot.data ?? [];
                if (absences.isEmpty) {
                  return const Text('No planned absences.', style: TextStyle(color: Colors.grey));
                }
                return Column(
                  children: absences.map((a) {
                    return ListTile(
                      leading: const Icon(Icons.event_busy),
                      title: Text('${a['start_date']} — ${a['end_date']}'),
                      subtitle: a['reason'] != null ? Text(a['reason'] as String) : null,
                    );
                  }).toList(),
                );
              },
            ),
            const Divider(height: 32),
            const Text('Attendance history', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 8),
            FutureBuilder<List<Map<String, dynamic>>>(
              future: _historyFuture,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 16),
                    child: Center(child: CircularProgressIndicator()),
                  );
                }
                if (snapshot.hasError) {
                  return Text('Failed to load: ${snapshot.error}');
                }
                final events = snapshot.data ?? [];
                if (events.isEmpty) {
                  return const Text('No attendance recorded yet.', style: TextStyle(color: Colors.grey));
                }
                return Column(
                  children: events.map((event) {
                    final flagged = event['flagged'] == true;
                    return ListTile(
                      leading: Icon(
                        event['type'] == 'drop_off' ? Icons.login : Icons.logout,
                        color: flagged ? Colors.red : null,
                      ),
                      title: Text(_formatEventType(event['type'] as String)),
                      subtitle: Text(
                        '${event['timestamp']}'
                        '${event['guardian_name'] != null ? ' — by ${event['guardian_name']}' : ''}'
                        '${flagged ? ' — FLAGGED' : ''}',
                      ),
                    );
                  }).toList(),
                );
              },
            ),
            // Bottom padding so the last item isn't hidden behind the FAB.
            const SizedBox(height: 80),
          ],
        ),
      ),
    );
  }
}

class _MarkAbsenceDialog extends StatefulWidget {
  final ParentApiClient apiClient;
  final String schoolSlug;
  final String studentId;

  const _MarkAbsenceDialog({
    required this.apiClient,
    required this.schoolSlug,
    required this.studentId,
  });

  @override
  State<_MarkAbsenceDialog> createState() => _MarkAbsenceDialogState();
}

class _MarkAbsenceDialogState extends State<_MarkAbsenceDialog> {
  DateTime? _startDate;
  DateTime? _endDate;
  final _reasonController = TextEditingController();
  bool _submitting = false;
  String? _error;

  Future<void> _pickDate({required bool isStart}) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: isStart ? (_startDate ?? now) : (_endDate ?? _startDate ?? now),
      firstDate: now.subtract(const Duration(days: 1)),
      lastDate: now.add(const Duration(days: 365)),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _startDate = picked;
        if (_endDate != null && _endDate!.isBefore(picked)) _endDate = picked;
      } else {
        _endDate = picked;
      }
    });
  }

  Future<void> _submit() async {
    if (_startDate == null || _endDate == null) {
      setState(() => _error = 'Pick a start and end date.');
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.apiClient.markExpectedAbsence(
        schoolSlug: widget.schoolSlug,
        studentId: widget.studentId,
        startDate: _startDate!,
        endDate: _endDate!,
        reason: _reasonController.text.trim(),
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      setState(() => _error = 'Failed: $e');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String _fmt(DateTime? d) => d == null ? 'Select date' : '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Mark a planned absence'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('Start: ${_fmt(_startDate)}'),
            trailing: const Icon(Icons.calendar_today),
            onTap: () => _pickDate(isStart: true),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('End: ${_fmt(_endDate)}'),
            trailing: const Icon(Icons.calendar_today),
            onTap: () => _pickDate(isStart: false),
          ),
          TextField(
            controller: _reasonController,
            decoration: const InputDecoration(labelText: 'Reason (optional)'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: Colors.red)),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: _submitting ? null : _submit,
          child: _submitting ? const CircularProgressIndicator() : const Text('Save'),
        ),
      ],
    );
  }
}
