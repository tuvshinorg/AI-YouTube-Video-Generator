import 'dart:io';

/// Simple date-rotated file logger — writes to the same folder the backend
/// logs to, so a user-reported failure can be traced across both files.
class AppLogger {
  static const _retentionDays = 7;
  static String? _logDir;
  static File? _file;

  static String get logDir {
    return _logDir ??= _initLogDir();
  }

  static String _initLogDir() {
    final base = Platform.environment['LOCALAPPDATA'] ?? Directory.systemTemp.path;
    final dir = '$base${Platform.pathSeparator}ytgen_manager${Platform.pathSeparator}logs';
    Directory(dir).createSync(recursive: true);
    return dir;
  }

  static void init() {
    _pruneOldLogs();
    _file = File('$logDir${Platform.pathSeparator}frontend-${_dateStamp(DateTime.now())}.log');
  }

  static void log(String message) {
    final line = '${DateTime.now().toIso8601String()} $message\n';
    try {
      _file?.writeAsStringSync(line, mode: FileMode.append);
    } catch (_) {
      // Logging must never crash the app.
    }
  }

  static void logRequest(String requestId, String method, String path, {int? statusCode, String? error}) {
    final suffix = error != null ? 'ERROR: $error' : 'HTTP $statusCode';
    log('[$requestId] $method $path -> $suffix');
  }

  static String _dateStamp(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}${d.month.toString().padLeft(2, '0')}${d.day.toString().padLeft(2, '0')}';

  static void _pruneOldLogs() {
    try {
      final cutoff = DateTime.now().subtract(const Duration(days: _retentionDays));
      for (final entity in Directory(logDir).listSync()) {
        if (entity is File && entity.path.contains('frontend-') && entity.statSync().modified.isBefore(cutoff)) {
          entity.deleteSync();
        }
      }
    } catch (_) {
      // Best-effort cleanup.
    }
  }
}
