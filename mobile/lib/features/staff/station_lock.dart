import 'package:flutter/material.dart';

/// Pieces shared by the pupil-card and guardian-QR gate stations: a locked,
/// front-camera screen left at the gate under a staff member's supervision.

/// Asks the supervising staff member to choose a 4-digit PIN to start station
/// mode. Returns the PIN, or null if they cancel.
Future<String?> promptSetStationPin(BuildContext context) async {
  final first = TextEditingController();
  final second = TextEditingController();
  String? error;
  final pin = await showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setLocal) => AlertDialog(
        title: const Text('Set a station PIN'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('You will need this PIN to leave station mode. Do not share it.'),
            TextField(
              controller: first,
              keyboardType: TextInputType.number,
              obscureText: true,
              maxLength: 4,
              decoration: const InputDecoration(labelText: '4-digit PIN', counterText: ''),
            ),
            TextField(
              controller: second,
              keyboardType: TextInputType.number,
              obscureText: true,
              maxLength: 4,
              decoration: const InputDecoration(labelText: 'Repeat PIN', counterText: ''),
            ),
            if (error != null)
              Padding(padding: const EdgeInsets.only(top: 8), child: Text(error!, style: const TextStyle(color: Colors.red))),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          TextButton(
            onPressed: () {
              if (!RegExp(r'^\d{4}$').hasMatch(first.text)) {
                setLocal(() => error = 'Enter exactly 4 digits');
              } else if (first.text != second.text) {
                setLocal(() => error = 'The PINs do not match');
              } else {
                Navigator.pop(ctx, first.text);
              }
            },
            child: const Text('Start'),
          ),
        ],
      ),
    ),
  );
  first.dispose();
  second.dispose();
  return pin;
}

/// Asks for the station PIN before leaving station mode. True once the right
/// PIN has been entered.
Future<bool> confirmLeaveStation(BuildContext context, String? pin) async {
  final controller = TextEditingController();
  bool wrong = false;
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => StatefulBuilder(
      builder: (ctx, setLocal) => AlertDialog(
        title: const Text('Leave station mode?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Enter the station PIN. Only the member of staff supervising the gate should leave this screen.'),
            TextField(
              controller: controller,
              keyboardType: TextInputType.number,
              obscureText: true,
              maxLength: 4,
              autofocus: true,
              decoration: InputDecoration(labelText: 'PIN', counterText: '', errorText: wrong ? 'Wrong PIN' : null),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Stay')),
          TextButton(
            onPressed: () {
              if (controller.text == pin) {
                Navigator.pop(ctx, true);
              } else {
                controller.clear();
                setLocal(() => wrong = true);
              }
            },
            child: const Text('Leave'),
          ),
        ],
      ),
    ),
  );
  controller.dispose();
  return ok == true;
}

/// A frame drawn over the camera view at a gate station, so the person knows
/// where to hold their card.
class StationFrameGuide extends StatelessWidget {
  final String message;
  const StationFrameGuide({super.key, this.message = 'Hold your card inside the box'});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 240,
              height: 240,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white, width: 4),
                borderRadius: BorderRadius.circular(20),
              ),
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(999)),
              child: Text(
                message,
                style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
