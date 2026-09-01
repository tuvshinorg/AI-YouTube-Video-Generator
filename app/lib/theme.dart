import 'package:flutter/material.dart';

/// Design tokens for the app, pulled from the product's mascot (blue/white
/// robot, YouTube-red camera, amber motion trail) rather than a generic
/// Material palette. One dark theme only — there's no light variant.
class AppColors {
  AppColors._();

  static const bgVoid = Color(0xFF090C10);
  static const panelBg = Color(0xFF101E1B);
  static const panelBgAlt = Color(0xFF0C1613);
  static const panelBorder = Color(0xFF1E332D);

  static const textPrimary = Color(0xFFEAF2F0);
  static const textMuted = Color(0xFF7E9A93);

  static const accentBlue = Color(0xFF31B6E8);
  static const accentRed = Color(0xFFE8362B);
  static const accentAmber = Color(0xFFF5A623);
  static const accentGreen = Color(0xFF3FBF8F);
  static const onAmber = Color(0xFF12100A);
}

/// Monospace "telemetry" text style — the small status-dot + stat-line
/// device used throughout (pipeline state, counts, timestamps, ids).
/// Consolas ships with every Windows install, so no font asset is needed.
const telemetryFont = 'Consolas';

TextStyle telemetryStyle({Color? color, double size = 12, FontWeight weight = FontWeight.w500}) => TextStyle(
      fontFamily: telemetryFont,
      fontSize: size,
      fontWeight: weight,
      color: color ?? AppColors.textMuted,
      letterSpacing: 0.1,
    );

/// A colored status dot + monospace label — the app's signature micro
/// element, echoed on every screen that reports live state.
class TelemetryPill extends StatelessWidget {
  final Color dotColor;
  final String label;
  final double fontSize;

  const TelemetryPill({super.key, required this.dotColor, required this.label, this.fontSize = 12});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 7,
          height: 7,
          margin: const EdgeInsets.only(right: 7),
          decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
        ),
        Text(label, style: telemetryStyle(size: fontSize)),
      ],
    );
  }
}

Color stageColor(String stage) {
  switch (stage) {
    case 'uploaded':
      return AppColors.accentGreen;
    case 'rendered':
    case 'ready-to-upload':
      return AppColors.accentBlue;
    case 'mixed':
    case 'transitioned':
      return AppColors.accentAmber;
    case 'error':
      return AppColors.accentRed;
    default:
      return AppColors.textMuted;
  }
}

ThemeData buildAppTheme() {
  const scheme = ColorScheme.dark(
    surface: AppColors.bgVoid,
    primary: AppColors.accentAmber,
    onPrimary: AppColors.onAmber,
    secondary: AppColors.accentBlue,
    onSecondary: Colors.black,
    error: AppColors.accentRed,
    onError: Colors.white,
    onSurface: AppColors.textPrimary,
  );

  final base = ThemeData(colorScheme: scheme, useMaterial3: true, scaffoldBackgroundColor: AppColors.bgVoid);

  return base.copyWith(
    textTheme: base.textTheme.apply(
      bodyColor: AppColors.textPrimary,
      displayColor: AppColors.textPrimary,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bgVoid,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      titleTextStyle: TextStyle(
        color: AppColors.textPrimary,
        fontSize: 20,
        fontWeight: FontWeight.w800,
        letterSpacing: -0.3,
      ),
      iconTheme: IconThemeData(color: AppColors.textPrimary),
    ),
    cardTheme: CardThemeData(
      color: AppColors.panelBg,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.panelBorder),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      iconColor: AppColors.textMuted,
      textColor: AppColors.textPrimary,
    ),
    dividerTheme: const DividerThemeData(color: AppColors.panelBorder, space: 32),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.panelBgAlt,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.panelBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.panelBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppColors.accentBlue, width: 1.5),
      ),
      labelStyle: const TextStyle(color: AppColors.textMuted),
      hintStyle: const TextStyle(color: AppColors.textMuted),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.accentAmber,
        foregroundColor: AppColors.onAmber,
        textStyle: const TextStyle(fontWeight: FontWeight.w800, letterSpacing: 0.2),
        padding: const EdgeInsets.symmetric(vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.textPrimary,
        side: const BorderSide(color: AppColors.panelBorder),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: AppColors.accentBlue),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: AppColors.panelBgAlt,
      side: const BorderSide(color: AppColors.panelBorder),
      labelStyle: const TextStyle(color: AppColors.textMuted, fontSize: 12),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.accentAmber),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.panelBg,
      indicatorColor: AppColors.accentAmber.withValues(alpha: 0.18),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 11,
          fontWeight: states.contains(WidgetState.selected) ? FontWeight.w700 : FontWeight.w500,
          color: states.contains(WidgetState.selected) ? AppColors.accentAmber : AppColors.textMuted,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected) ? AppColors.accentAmber : AppColors.textMuted,
        ),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.panelBg,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppColors.panelBorder),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.panelBgAlt,
      contentTextStyle: const TextStyle(color: AppColors.textPrimary),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      behavior: SnackBarBehavior.floating,
    ),
  );
}
