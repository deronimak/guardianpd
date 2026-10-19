import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/offline_scan_store.dart';

String _tokenFor(Map<String, dynamic> payload) {
  final body = base64Url.encode(utf8.encode(jsonEncode(payload))).replaceAll('=', '');
  return '$body.signature';
}

void main() {
  test('reads the pupil id from a card token without verifying it', () {
    final token = _tokenFor({'pid': 'abc-123', 'sid': 's', 'n': 'x'});
    expect(OfflineScanStore.pupilIdFromToken(token), 'abc-123');
  });

  test('a guardian token or garbage is not a pupil card', () {
    expect(OfflineScanStore.pupilIdFromToken(_tokenFor({'gid': 'g', 'sid': 's', 'n': 'x'})), isNull);
    expect(OfflineScanStore.pupilIdFromToken('not-a-token'), isNull);
    expect(OfflineScanStore.pupilIdFromToken(''), isNull);
  });

  test('queue keeps rejected scans for review and drops accepted ones', () async {
    final store = OfflineScanStore.forSchool('unit-test-school');
    await store.load();
    store.roster = {
      'p1': {'id': 'p1', 'name': 'Ada Pupil'},
    };
    final good = {'token': _tokenFor({'pid': 'p1'}), 'scanned_at': '2026-10-14T07:30:00Z'};
    final bad = {'token': _tokenFor({'pid': 'zzz'}), 'scanned_at': '2026-10-14T07:31:00Z'};
    store.queue = [good, bad];

    await store.applyBatchResults(
      [good, bad],
      [
        {'status': 'recorded'},
        {'status': 'rejected', 'detail': 'This card is unrecognized or has been replaced'},
      ],
    );

    expect(store.queue, isEmpty);
    expect(store.rejected, hasLength(1));
    expect(store.rejected.first['detail'], contains('replaced'));
  });
  test('only pupils whose cached photo is missing or out of date need a download', () async {
    final store = OfflineScanStore.forSchool('unit-test-photos');
    await store.load();
    store.roster = {
      'a': {'id': 'a', 'name': 'A', 'photo_hash': 'h1'},
      'b': {'id': 'b', 'name': 'B', 'photo_hash': 'h2'},
      'c': {'id': 'c', 'name': 'C', 'photo_hash': null},
    };
    store.photoHashes = {'a': 'h1', 'b': 'old'};
    expect(store.pupilsNeedingPhoto().map((p) => p['id']), ['b']);
  });
  test('offline suggestion alternates from the last saved scan today, defaulting to arrived', () async {
    final store = OfflineScanStore.forSchool('unit-test-suggest');
    await store.load();
    final now = DateTime.now();
    final token = _tokenFor({'pid': 'pupil-1'});
    store.queue = [];
    expect(store.suggestedTypeFor('pupil-1', now), 'drop_off');

    store.queue = [
      {'token': token, 'scanned_at': now.subtract(const Duration(minutes: 5)).toUtc().toIso8601String(), 'type': 'drop_off'},
    ];
    expect(store.suggestedTypeFor('pupil-1', now), 'pick_up');

    store.queue.add({'token': token, 'scanned_at': now.toUtc().toIso8601String(), 'type': 'pick_up'});
    expect(store.suggestedTypeFor('pupil-1', now), 'drop_off');

    // Another pupil, or a scan from a different day, doesn't count.
    expect(store.suggestedTypeFor('pupil-2', now), 'drop_off');
    store.queue = [
      {'token': token, 'scanned_at': now.subtract(const Duration(days: 2)).toUtc().toIso8601String(), 'type': 'drop_off'},
    ];
    expect(store.suggestedTypeFor('pupil-1', now), 'drop_off');
  });
  test('reads the guardian id from a guardian card token; a pupil card is not one', () {
    expect(OfflineScanStore.guardianIdFromToken(_tokenFor({'gid': 'g-1', 'sid': 's', 'n': 'x'})), 'g-1');
    expect(OfflineScanStore.guardianIdFromToken(_tokenFor({'pid': 'p-1', 'sid': 's', 'n': 'x'})), isNull);
    expect(OfflineScanStore.guardianIdFromToken('garbage'), isNull);
  });

  test('saved guardian scans leave the queue once uploaded; unauthorized ones are kept for review', () async {
    final store = OfflineScanStore.forSchool('unit-test-guardian-queue');
    await store.load();
    final token = _tokenFor({'gid': 'g-1'});
    final fine = {
      'token': token, 'student_id': 's1', 'type': 'drop_off', 'scanned_at': '2026-10-14T07:30:00Z',
      'guardian_name': 'Mrs Offline', 'student_name': 'Kid One',
    };
    final bad = {
      'token': token, 'student_id': 's2', 'type': 'pick_up', 'scanned_at': '2026-10-14T14:00:00Z',
      'guardian_name': 'Mrs Offline', 'student_name': 'Someone Else',
    };
    store.guardianQueue = [fine, bad];
    store.rejected = [];

    await store.applyGuardianBatchResults(
      [fine, bad],
      [
        {'status': 'recorded'},
        {'status': 'flagged', 'detail': 'This guardian is not authorized for this child'},
      ],
    );

    expect(store.guardianQueue, isEmpty);
    expect(store.rejected, hasLength(1));
    expect(store.rejected.first['name'], 'Mrs Offline / Someone Else');
    expect(store.rejected.first['detail'], contains('not authorized'));
  });
}
