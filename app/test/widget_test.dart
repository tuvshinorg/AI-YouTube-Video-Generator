import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:ytgen_manager/main.dart';

void main() {
  testWidgets('App launches to the Dashboard tab', (WidgetTester tester) async {
    await tester.pumpWidget(const YtGenManagerApp());
    await tester.pump();

    expect(find.text('Dashboard'), findsAtLeastNWidgets(1));
    expect(find.text('Add Text'), findsAtLeastNWidgets(1));
    expect(find.text('Queue'), findsAtLeastNWidgets(1));
    expect(find.text('Videos'), findsAtLeastNWidgets(1));

    // Dispose the widget tree so the dashboard's periodic refresh timer is
    // cancelled before the test ends.
    await tester.pumpWidget(const SizedBox());
  });
}
