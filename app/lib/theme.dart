import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Design tokens for the app. True-neutral dark surfaces (no teal/green
/// cast) with one signature brand accent (amber) plus semantic state colors
/// pulled from the same family Apple uses for its own system palette — so
/// they read as considered states, not a rainbow. One dark theme only —
/// there's no light variant.
class AppColors {
  AppColors._();

  static const bgVoid = Color(0xFF111113);
  static const panelBg = Color(0xFF1B1B1F);
  static const panelBgAlt = Color(0xFF19191C);
  // Row hover/pressed state inside a grouped list — replaces a stroked
  // border as the way surfaces separate from each other.
  static const surfaceRaised = Color(0xFF25252A);
  // Hairline divider between rows in a grouped list. Expressed as a low-
  // alpha white so it reads correctly regardless of which surface it sits
  // on, the way a real hairline does.
  static const hairline = Color(0x1FFFFFFF);

  static const textPrimary = Color(0xFFF5F5F7);
  static const textMuted = Color(0xFF96969E);

  static const accentBlue = Color(0xFF0A84FF);
  static const accentRed = Color(0xFFFF453A);
  static const accentAmber = Color(0xFFFFB646);
  static const accentGreen = Color(0xFF30D158);
  static const onAmber = Color(0xFF241A06);

  // Kept for the one legacy caller (panelBorder-as-1px-rule in home_shell's
  // AppBar bottom line); everywhere a card/list border used to live, use
  // background-tone separation (panelBgAlt/surfaceRaised) or hairline
  // instead.
  static const panelBorder = hairline;
}

/// Monospace face — reserved for the few places text is genuinely terminal
/// output or a literal code (the pipeline's raw log tail, a device-login
/// code). Everywhere else (stats, timestamps, counts) uses the UI face with
/// tabular figures instead, so numbers still line up without the whole app
/// reading as a dev console. Exposed directly (not just via [consoleStyle])
/// for the couple of `const TextStyle(...)` call sites that need it.
const consoleFont = 'Consolas';

TextStyle consoleStyle({Color? color, double size = 12, FontWeight weight = FontWeight.w500}) => TextStyle(
      fontFamily: consoleFont,
      fontSize: size,
      fontWeight: weight,
      color: color ?? AppColors.textMuted,
      letterSpacing: 0.1,
    );

/// Small stat/timestamp/count text — the UI face (Inter, via the app theme)
/// with tabular figures so numbers stay aligned wherever they appear.
TextStyle telemetryStyle({Color? color, double size = 12, FontWeight weight = FontWeight.w500}) => TextStyle(
      fontSize: size,
      fontWeight: weight,
      color: color ?? AppColors.textMuted,
      letterSpacing: 0.1,
      fontFeatures: const [FontFeature.tabularFigures()],
    );

/// A colored status dot + label — the app's signature micro element, echoed
/// on every screen that reports live state.
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

/// Rough completion fraction for a stage — feeds the small per-row
/// [StageRing] fill. Approximate by design: the exact percent lives only in
/// the single active pipeline run's status payload, not per queued project.
double stageProgress(String stage) {
  switch (stage) {
    case 'uploaded':
      return 1.0;
    case 'rendered':
    case 'ready-to-upload':
      return 0.9;
    case 'mixed':
      return 0.7;
    case 'transitioned':
      return 0.55;
    case 'error':
      return 1.0;
    default:
      return 0.15;
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

  // Inter — the closest open, embeddable match to SF Pro's proportions.
  // Applying it once here at the TextTheme level cascades to every plain
  // `TextStyle(...)` used throughout the app too: a Text widget merges its
  // own style over the ambient DefaultTextStyle (derived from this
  // TextTheme), and merge() only overrides fields the caller actually set —
  // so any inline style that doesn't specify fontFamily inherits Inter
  // automatically, with no need to touch every call site.
  final textTheme = GoogleFonts.interTextTheme(base.textTheme).apply(
    bodyColor: AppColors.textPrimary,
    displayColor: AppColors.textPrimary,
  );

  return base.copyWith(
    textTheme: textTheme,
    appBarTheme: AppBarTheme(
      backgroundColor: AppColors.bgVoid,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      titleTextStyle: GoogleFonts.inter(
        color: AppColors.textPrimary,
        fontSize: 17,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
      ),
      iconTheme: const IconThemeData(color: AppColors.textPrimary),
    ),
    cardTheme: CardThemeData(
      color: AppColors.panelBg,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    hoverColor: AppColors.surfaceRaised,
    listTileTheme: const ListTileThemeData(
      iconColor: AppColors.textMuted,
      textColor: AppColors.textPrimary,
    ),
    dividerTheme: const DividerThemeData(color: AppColors.hairline, space: 32, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.panelBgAlt,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
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
        textStyle: const TextStyle(fontWeight: FontWeight.w700, letterSpacing: 0.1),
        padding: const EdgeInsets.symmetric(vertical: 15),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.textPrimary,
        side: const BorderSide(color: AppColors.hairline),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: AppColors.accentBlue),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: AppColors.panelBgAlt,
      side: BorderSide.none,
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
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.surfaceRaised,
      contentTextStyle: const TextStyle(color: AppColors.textPrimary),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      behavior: SnackBarBehavior.floating,
    ),
  );
}
