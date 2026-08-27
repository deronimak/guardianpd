// Navigation smoke tests for the role-select entry point (lib/main.dart /
// lib/features/auth/role_select_screen.dart). The old default counter test
// this file replaced no longer applied — MyApp doesn't have a counter.
//
// These stop at each login screen rather than logging in, since login
// makes a real network call (ApiClient) which isn't available in a widget
// test — that's covered on the backend side instead (backend/tests/).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:mobile/main.dart';

void main() {
  testWidgets('Role select screen shows all three role buttons', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('School Attendance'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'School Admin'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'School Staff'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Guardian'), findsOneWidget);
  });

  testWidgets('Tapping School Admin opens the admin login form', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    await tester.tap(find.widgetWithText(ElevatedButton, 'School Admin'));
    await tester.pumpAndSettle();

    expect(find.text('School Admin Login'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(3)); // school slug, email, password
  });

  testWidgets('Tapping School Staff opens the staff login form', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    await tester.tap(find.widgetWithText(ElevatedButton, 'School Staff'));
    await tester.pumpAndSettle();

    expect(find.text('School Staff Login'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(3)); // school slug, username, password
  });

  testWidgets('Tapping Guardian opens the guardian login form', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    await tester.tap(find.widgetWithText(ElevatedButton, 'Guardian'));
    await tester.pumpAndSettle();

    expect(find.text('Guardian Login'), findsOneWidget);
    expect(find.byType(TextField), findsNWidgets(2)); // email, password
    expect(find.text("First time? Activate your account"), findsOneWidget);
  });
}
