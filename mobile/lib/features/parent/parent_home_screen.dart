import 'package:flutter/material.dart';

import '../../core/parent_api_client.dart';
import '../../core/push_registration.dart';
import 'student_detail_screen.dart';

/// Shows every child linked to this parent, aggregated across schools by
/// the backend (ARCHITECTURE.md §2/§8). Tap a child for attendance history
/// and planned-absence marking.
class ParentHomeScreen extends StatefulWidget {
  final ParentApiClient apiClient;
  const ParentHomeScreen({super.key, required this.apiClient});

  @override
  State<ParentHomeScreen> createState() => _ParentHomeScreenState();
}

class _ParentHomeScreenState extends State<ParentHomeScreen> {
  late Future<List<Map<String, dynamic>>> _childrenFuture;
  // Why this phone can't get notifications, if it can't (null = fine).
  String? _pushProblem;
  bool _pushRetrying = false;

  @override
  void initState() {
    super.initState();
    _childrenFuture = widget.apiClient.myChildren();
    // Fire-and-forget: push registration failing shouldn't block the
    // parent from seeing their children list.
    _registerPush();
  }

  Future<void> _registerPush() async {
    setState(() => _pushRetrying = true);
    final problem = await initializeAndRegisterPush(widget.apiClient);
    if (mounted) {
      setState(() {
        _pushProblem = problem;
        _pushRetrying = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Children')),
      body: Column(
        children: [
          if (_pushProblem != null)
            Material(
              color: Colors.amber.shade100,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 8, 10),
                child: Row(
                  children: [
                    const Icon(Icons.notifications_off, size: 20),
                    const SizedBox(width: 10),
                    Expanded(child: Text(_pushProblem!, style: const TextStyle(fontSize: 13))),
                    TextButton(
                      onPressed: _pushRetrying ? null : _registerPush,
                      child: Text(_pushRetrying ? '...' : 'Retry'),
                    ),
                  ],
                ),
              ),
            ),
          Expanded(child: _buildChildren()),
        ],
      ),
    );
  }

  Widget _buildChildren() {
    return FutureBuilder<List<Map<String, dynamic>>>(
        future: _childrenFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Text('Failed to load: ${snapshot.error}'));
          }
          final children = snapshot.data ?? [];
          if (children.isEmpty) {
            return const Center(child: Text('No children linked yet.'));
          }
          return ListView.builder(
            itemCount: children.length,
            itemBuilder: (context, index) {
              final child = children[index];
              return ListTile(
                title: Text(child['student_name'] as String? ?? ''),
                subtitle: Text(
                  '${child['school_name'] ?? ''}'
                  '${child['grade'] != null ? ' — ${child['grade']}' : ''}',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => StudentDetailScreen(
                      apiClient: widget.apiClient,
                      schoolSlug: child['school_slug'] as String,
                      studentId: child['student_id'] as String,
                      studentName: child['student_name'] as String? ?? '',
                    ),
                  ),
                ),
              );
            },
          );
        },
    );
  }
}
