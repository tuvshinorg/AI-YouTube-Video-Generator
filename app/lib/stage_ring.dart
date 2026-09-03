import 'package:flutter/material.dart';

/// The app's signature status element — a tinted progress ring, used at two
/// scales: small as the leading indicator on every list row, and large in
/// the status panel. One motif standing in for both a `Chip` label and a
/// `LinearProgressIndicator` bar, so the whole system reads as one thing
/// instead of three different ways of showing "how far along".
///
/// [value] null means indeterminate — draws Flutter's own animated spinner
/// (correct motion, respects reduced-motion) instead of a static fraction.
class StageRing extends StatelessWidget {
  final double size;
  final double strokeWidth;
  final double? value;
  final Color color;
  final Color? trackColor;
  final Widget? child;

  const StageRing({
    super.key,
    required this.size,
    required this.color,
    this.strokeWidth = 3,
    this.value,
    this.trackColor,
    this.child,
  });

  @override
  Widget build(BuildContext context) {
    final track = trackColor ?? color.withValues(alpha: 0.16);
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CustomPaint(size: Size(size, size), painter: _RingTrackPainter(color: track, strokeWidth: strokeWidth)),
          SizedBox(
            width: size,
            height: size,
            child: CircularProgressIndicator(
              value: value,
              strokeWidth: strokeWidth,
              strokeCap: StrokeCap.round,
              valueColor: AlwaysStoppedAnimation(color),
              backgroundColor: Colors.transparent,
            ),
          ),
          ?child,
        ],
      ),
    );
  }
}

class _RingTrackPainter extends CustomPainter {
  final Color color;
  final double strokeWidth;
  const _RingTrackPainter({required this.color, required this.strokeWidth});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;
    canvas.drawArc(Offset.zero & size, 0, 6.28319, false, paint);
  }

  @override
  bool shouldRepaint(covariant _RingTrackPainter oldDelegate) =>
      oldDelegate.color != color || oldDelegate.strokeWidth != strokeWidth;
}
