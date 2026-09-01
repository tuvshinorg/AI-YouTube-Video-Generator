import 'dart:async';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';

import 'api_client.dart';
import 'app_logger.dart';
import 'backend_launcher.dart';
import 'home_shell.dart';
import 'theme.dart';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  AppLogger.init();

  final devFlag = args.contains('--dev');

  BackendHandle handle;
  try {
    handle = await BackendLauncher.start(devFlag: devFlag);
  } catch (e) {
    AppLogger.log('Backend startup failed: $e');
    runApp(_StartupErrorApp(error: e, devFlag: devFlag));
    return;
  }

  ApiConfig.configure(handle);
  AppLogger.log('Backend ready at ${handle.baseUrl} (pid ${handle.process?.pid ?? "dev-mode"})');

  runApp(const YtGenManagerApp());

  AppLifecycleListener(
    onExitRequested: () async {
      await BackendLauncher.shutdown(handle);
      return AppExitResponse.exit;
    },
  );

  Timer.periodic(const Duration(seconds: 20), (_) => ApiClient().heartbeat());
}

class YtGenManagerApp extends StatelessWidget {
  const YtGenManagerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Shorts Factory',
      theme: buildAppTheme(),
      themeMode: ThemeMode.dark,
      home: const HomeShell(),
    );
  }
}

/// Shown instead of a blank screen or spinner when the backend never became
/// ready — always has a concrete message plus its recent stderr.
class _StartupErrorApp extends StatelessWidget {
  final Object error;
  final bool devFlag;

  const _StartupErrorApp({required this.error, required this.devFlag});

  @override
  Widget build(BuildContext context) {
    final message = error is BackendStartupException ? (error as BackendStartupException).toString() : error.toString();

    return MaterialApp(
      theme: buildAppTheme(),
      themeMode: ThemeMode.dark,
      home: Scaffold(
        appBar: AppBar(title: const Text('Could not start')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error, size: 32),
                  const SizedBox(width: 12),
                  const Expanded(child: Text('The backend failed to start', style: TextStyle(fontSize: 20))),
                ],
              ),
              const SizedBox(height: 16),
              Expanded(
                child: SingleChildScrollView(
                  child: SelectableText(message, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
                ),
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: () => main(devFlag ? const ['--dev'] : const []),
                icon: const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
