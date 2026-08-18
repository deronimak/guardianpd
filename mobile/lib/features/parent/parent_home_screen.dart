import 'package:flutter/material.dart';

import '../../core/parent_api_client.dart';

/// Shows every child linked to this parent, aggregated across schools by
/// the backend (ARCHITECTURE.md §2/§8). Attendance history, planned-absence
/// marking, and notification preferences aren't built yet.
class ParentHomeScreen extends StatefulWidget {
  final ParentApiClient apiClient;
  const ParentHomeScreen({super.key, required this.apiClient});

  @override
  State<ParentHomeScreen> createState() => _ParentHomeScreenState();
}

class _ParentHomeScreenState extends State<ParentHomeScreen> {
  late Future<List<Map<String, dynamic>>> _childrenFuture;

  @override
  void initState() {
    super.initState();
    _childrenFuture = widget.apiClient.myChildren();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Children')),
      body: FutureBuilder<List<Map<String, dynamic>>>(
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
              );
            },
          );
        },
      ),
    );
  }
}
