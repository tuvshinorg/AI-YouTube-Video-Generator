// ignore_for_file: camel_case_types
import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:math';

import 'package:ffi/ffi.dart' as pkg_ffi;
import 'package:http/http.dart' as http;
import 'package:win32/win32.dart';

/// Thrown when the backend process cannot be started or never becomes ready.
/// Always carries the last lines of its stderr so the caller can show a real
/// error instead of a blank screen or a spinner.
class BackendStartupException implements Exception {
  final String message;
  final List<String> stderrTail;
  BackendStartupException(this.message, this.stderrTail);

  @override
  String toString() => stderrTail.isEmpty ? message : '$message\n\n${stderrTail.join('\n')}';
}

/// The live connection to a running backend: where it is, how to authenticate
/// to it, and (in production) the process Dart itself spawned.
class BackendHandle {
  final String baseUrl;
  final String token;
  final Process? process; // null in dev mode, where we connect but didn't spawn it.
  final List<String> stderrTail;

  BackendHandle({required this.baseUrl, required this.token, this.process, required this.stderrTail});
}

class _EarlyExit {
  final int code;
  _EarlyExit(this.code);
}

class _HandshakeTimeout {}

/// Win32 struct not shipped by package:win32 6.4.0 — hand-defined here from
/// the stable MSDN layout (unchanged since Windows Vista) because setting
/// JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE requires passing this exact shape to
/// SetInformationJobObject.
final class _JOBOBJECT_BASIC_LIMIT_INFORMATION extends Struct {
  @Int64()
  external int perProcessUserTimeLimit;
  @Int64()
  external int perJobUserTimeLimit;
  @Uint32()
  external int limitFlags;
  @IntPtr()
  external int minimumWorkingSetSize;
  @IntPtr()
  external int maximumWorkingSetSize;
  @Uint32()
  external int activeProcessLimit;
  @IntPtr()
  external int affinity;
  @Uint32()
  external int priorityClass;
  @Uint32()
  external int schedulingClass;
}

final class _IO_COUNTERS extends Struct {
  @Uint64()
  external int readOperationCount;
  @Uint64()
  external int writeOperationCount;
  @Uint64()
  external int otherOperationCount;
  @Uint64()
  external int readTransferCount;
  @Uint64()
  external int writeTransferCount;
  @Uint64()
  external int otherTransferCount;
}

final class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION extends Struct {
  external _JOBOBJECT_BASIC_LIMIT_INFORMATION basicLimitInformation;
  external _IO_COUNTERS ioInfo;
  @IntPtr()
  external int processMemoryLimit;
  @IntPtr()
  external int jobMemoryLimit;
  @IntPtr()
  external int peakProcessMemoryUsed;
  @IntPtr()
  external int peakJobMemoryUsed;
}

const int _jobObjectLimitKillOnJobClose = 0x2000;
const int _processTerminate = 0x0001;
const int _processSetQuota = 0x0100;

/// Ties the backend's lifetime to ours via a Windows Job Object: if this app
/// is force-killed (Task Manager, crash, debugger detach) and never runs its
/// own shutdown code, Windows kills the backend anyway. The job/process
/// handles are intentionally never closed — closing the job handle is what
/// triggers the kill, so it must stay open for the app's entire lifetime;
/// the OS reclaims both handles when this process exits either way.
void _attachJobObject(int backendPid) {
  if (!Platform.isWindows) return;

  final jobResult = CreateJobObject(null, null);
  if (jobResult.value.address == 0) return;
  final job = jobResult.value;

  final infoPtr = pkg_ffi.calloc<_JOBOBJECT_EXTENDED_LIMIT_INFORMATION>();
  infoPtr.ref.basicLimitInformation.limitFlags = _jobObjectLimitKillOnJobClose;
  SetInformationJobObject(
    job,
    JobObjectExtendedLimitInformation,
    infoPtr.cast(),
    sizeOf<_JOBOBJECT_EXTENDED_LIMIT_INFORMATION>(),
  );
  pkg_ffi.calloc.free(infoPtr);

  final procResult = OpenProcess(
    PROCESS_ACCESS_RIGHTS(_processTerminate | _processSetQuota),
    false,
    backendPid,
  );
  if (procResult.value.address == 0) return;
  AssignProcessToJobObject(job, procResult.value);
}

class BackendLauncher {
  static const _handshakeTimeout = Duration(seconds: 20);
  static const _stderrTailLines = 20;

  /// Starts (or, in dev mode, connects to) the backend. Always returns a
  /// ready-to-use [BackendHandle] or throws [BackendStartupException] with a
  /// human-readable message and the backend's recent stderr — never leaves
  /// the caller to show a blank screen or spin forever.
  static Future<BackendHandle> start({required bool devFlag}) async {
    if (devFlag) {
      final devUrl = Platform.environment['YTGEN_BACKEND_URL'];
      if (devUrl != null && devUrl.isNotEmpty) {
        final devToken = Platform.environment['YTGEN_BACKEND_TOKEN'] ?? '';
        return BackendHandle(baseUrl: devUrl, token: devToken, stderrTail: const []);
      }
    }

    final exePath = _locateBackendExe();
    final token = _generateToken();

    Process process;
    try {
      process = await Process.start(exePath, ['--port', '0', '--token', token]);
    } catch (e) {
      throw BackendStartupException('Could not launch backend at $exePath:\n$e', const []);
    }

    final stderrTail = <String>[];
    process.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      stderrTail.add(line);
      if (stderrTail.length > _stderrTailLines) stderrTail.removeAt(0);
    });

    final handshakeCompleter = Completer<Map<String, dynamic>>();
    final stdoutSub = process.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (handshakeCompleter.isCompleted) return;
      try {
        final parsed = jsonDecode(line);
        if (parsed is Map && parsed.containsKey('port') && parsed.containsKey('pid')) {
          handshakeCompleter.complete(Map<String, dynamic>.from(parsed));
        }
      } catch (_) {
        // Not the handshake line — noise, not an error.
      }
    });

    final exitedCompleter = Completer<int>();
    unawaited(process.exitCode.then((code) {
      if (!exitedCompleter.isCompleted) exitedCompleter.complete(code);
    }));

    final Object result = await Future.any<Object>([
      handshakeCompleter.future,
      exitedCompleter.future.then((code) => _EarlyExit(code)),
      Future.delayed(_handshakeTimeout).then((_) => _HandshakeTimeout()),
    ]);

    if (result is _EarlyExit) {
      await stdoutSub.cancel();
      throw BackendStartupException(
        'Backend exited immediately (code ${result.code}) before it was ready.',
        List.of(stderrTail),
      );
    }
    if (result is _HandshakeTimeout) {
      process.kill(ProcessSignal.sigterm);
      await Future.delayed(const Duration(milliseconds: 300));
      process.kill(ProcessSignal.sigkill);
      await stdoutSub.cancel();
      throw BackendStartupException(
        'Backend did not start within ${_handshakeTimeout.inSeconds}s.',
        List.of(stderrTail),
      );
    }

    final handshake = result as Map<String, dynamic>;
    final port = handshake['port'] as int;
    _attachJobObject(process.pid);

    return BackendHandle(baseUrl: 'http://127.0.0.1:$port', token: token, process: process, stderrTail: stderrTail);
  }

  /// Graceful shutdown: ask nicely, wait up to 3s, then force-kill. No-op in
  /// dev mode, where we never spawned the process in the first place.
  static Future<void> shutdown(BackendHandle handle) async {
    final process = handle.process;
    if (process == null) return;

    try {
      await http
          .post(Uri.parse('${handle.baseUrl}/shutdown'), headers: {'Authorization': 'Bearer ${handle.token}'})
          .timeout(const Duration(seconds: 2));
    } catch (_) {
      // Backend may already be gone — fall through to the exit-code wait.
    }

    final exitCode = await process.exitCode.timeout(const Duration(seconds: 3), onTimeout: () => -1);
    if (exitCode == -1) {
      process.kill(ProcessSignal.sigkill);
    }
  }

  static String _locateBackendExe() {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final candidate = '$exeDir${Platform.pathSeparator}backend.exe';
    if (File(candidate).existsSync()) return candidate;
    throw BackendStartupException(
      'backend.exe not found next to the app (looked in $exeDir).\n'
      'Run "make backend-exe" to build it, or set YTGEN_BACKEND_URL to use dev mode.',
      const [],
    );
  }

  static String _generateToken() {
    final rand = Random.secure();
    final bytes = List<int>.generate(32, (_) => rand.nextInt(256));
    return bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  }
}
