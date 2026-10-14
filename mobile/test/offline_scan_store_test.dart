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
}
