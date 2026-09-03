import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

import 'app_logger.dart';
import 'backend_launcher.dart';

/// Thrown whenever the backend returns an error envelope, a non-2xx response
/// it couldn't decode, or the request itself fails (backend unreachable).
class ApiException implements Exception {
  final String message;
  final String? code;
  ApiException(this.message, {this.code});
  @override
  String toString() => message;
}

/// Holds the live backend connection — set once at startup from the
/// [BackendHandle] returned by [BackendLauncher.start]. Not user-editable:
/// the app owns the backend's lifetime, so there's no persisted URL to type.
class ApiConfig {
  static String baseUrl = '';
  static String token = '';
  static int? pid;
  static BackendHandle? handle;

  static void configure(BackendHandle h) {
    handle = h;
    baseUrl = h.baseUrl;
    token = h.token;
    pid = h.process?.pid;
  }
}

String _newRequestId() {
  final rand = Random();
  return List.generate(8, (_) => rand.nextInt(16).toRadixString(16)).join();
}

/// Thin REST client for the AI YouTube Video Generator API (see api.py).
class ApiClient {
  static const _connectTimeout = Duration(seconds: 5);
  static const _requestTimeout = Duration(seconds: 30);

  static final http.Client _client = IOClient(HttpClient()..connectionTimeout = _connectTimeout);

  Uri _uri(String path) => Uri.parse('${ApiConfig.baseUrl}$path');

  Map<String, String> _headers([Map<String, String>? extra]) => {
        if (ApiConfig.token.isNotEmpty) 'Authorization': 'Bearer ${ApiConfig.token}',
        'X-Request-Id': _newRequestId(),
        ...?extra,
      };

  Future<dynamic> _get(String path) async {
    final headers = _headers();
    final reqId = headers['X-Request-Id']!;
    http.Response res;
    try {
      res = await _client.get(_uri(path), headers: headers).timeout(_requestTimeout);
    } catch (e) {
      AppLogger.logRequest(reqId, 'GET', path, error: e.toString());
      throw ApiException('Could not reach backend at ${ApiConfig.baseUrl}\n$e');
    }
    AppLogger.logRequest(reqId, 'GET', path, statusCode: res.statusCode);
    return _decode(res);
  }

  Future<dynamic> _post(String path, [Map<String, dynamic>? body]) async {
    final headers = _headers({'Content-Type': 'application/json'});
    final reqId = headers['X-Request-Id']!;
    http.Response res;
    try {
      res = await _client.post(_uri(path), headers: headers, body: jsonEncode(body ?? {})).timeout(_requestTimeout);
    } catch (e) {
      AppLogger.logRequest(reqId, 'POST', path, error: e.toString());
      throw ApiException('Could not reach backend at ${ApiConfig.baseUrl}\n$e');
    }
    AppLogger.logRequest(reqId, 'POST', path, statusCode: res.statusCode);
    return _decode(res);
  }

  Future<dynamic> _delete(String path) async {
    final headers = _headers();
    final reqId = headers['X-Request-Id']!;
    http.Response res;
    try {
      res = await _client.delete(_uri(path), headers: headers).timeout(_requestTimeout);
    } catch (e) {
      AppLogger.logRequest(reqId, 'DELETE', path, error: e.toString());
      throw ApiException('Could not reach backend at ${ApiConfig.baseUrl}\n$e');
    }
    AppLogger.logRequest(reqId, 'DELETE', path, statusCode: res.statusCode);
    return _decode(res);
  }

  dynamic _decode(http.Response res) {
    if (res.statusCode >= 200 && res.statusCode < 300) {
      if (res.body.isEmpty) return null;
      return jsonDecode(res.body);
    }

    String message = 'HTTP ${res.statusCode}';
    String? code;
    try {
      final parsed = jsonDecode(res.body);
      final error = parsed is Map ? parsed['error'] : null;
      if (error is Map) {
        message = (error['message'] ?? message).toString();
        code = error['code']?.toString();
      }
    } catch (_) {
      // Body wasn't the expected envelope — fall back to the raw status.
    }
    throw ApiException(message, code: code);
  }

  Future<Map<String, dynamic>> getStatus() async => Map<String, dynamic>.from(await _get('/api/status'));

  Future<Map<String, dynamic>> getCodexStatus() async => Map<String, dynamic>.from(await _get('/api/codex/status'));

  /// Starts a new Codex device-auth login. NOTE: this immediately
  /// invalidates whatever Codex session was previously logged in, even if
  /// this new one is never completed — only call it when the user has
  /// explicitly asked to log in.
  Future<Map<String, dynamic>> loginCodex() async => Map<String, dynamic>.from(await _post('/api/codex/login'));

  Future<Map<String, dynamic>> getPipelineStatus() async => Map<String, dynamic>.from(await _get('/api/pipeline/status'));

  Future<Map<String, dynamic>> getQueue() async => Map<String, dynamic>.from(await _get('/api/queue'));

  Future<Map<String, dynamic>> addText(String text, {String? title, String group = 'manual'}) async =>
      Map<String, dynamic>.from(await _post('/api/text', {
        'text': text,
        if (title != null && title.isNotEmpty) 'title': title,
        'group': group,
      }));

  Future<Map<String, dynamic>> retrySeed(int seedId) async => Map<String, dynamic>.from(await _post('/api/seeds/$seedId/retry'));

  Future<Map<String, dynamic>> getQueueEntry(int queueId) async => Map<String, dynamic>.from(await _get('/api/queue/$queueId'));

  Future<Map<String, dynamic>> deleteQueueEntry(int queueId) async => Map<String, dynamic>.from(await _delete('/api/queue/$queueId'));

  Future<Map<String, dynamic>> getSeedDetail(int seedId) async => Map<String, dynamic>.from(await _get('/api/seeds/$seedId'));

  Future<Map<String, dynamic>> deleteSeed(int seedId) async => Map<String, dynamic>.from(await _delete('/api/seeds/$seedId'));

  Future<Map<String, dynamic>> runPipeline(String output) async =>
      Map<String, dynamic>.from(await _post('/api/pipeline/run', {'output': output}));

  Future<Map<String, dynamic>> stopPipeline() async => Map<String, dynamic>.from(await _post('/api/pipeline/stop'));

  Future<void> heartbeat() async {
    try {
      await _post('/heartbeat');
    } catch (_) {
      // Best-effort — the backend's own watchdog just fires if these stop.
    }
  }

  Future<List<dynamic>> getVideos() async => List<dynamic>.from(await _get('/api/videos'));

  // Opened externally via url_launcher (system video player/browser), which
  // can't attach an Authorization header — the token travels as a query
  // param instead; the backend accepts either for this one route.
  String videoUrl(int seedId) =>
      '${ApiConfig.baseUrl}/api/videos/$seedId/file${ApiConfig.token.isNotEmpty ? '?token=${ApiConfig.token}' : ''}';
}
