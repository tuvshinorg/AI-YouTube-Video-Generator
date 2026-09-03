import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'api_client.dart';
import 'app_logger.dart';
import 'backend_launcher.dart';
import 'theme.dart';

/// Connection diagnostics + AI provider status. The app owns the backend's
/// lifetime now (spawned with a random port + token at startup), so there's
/// nothing to type for the connection — just what's currently connected,
/// a way to restart it, find the logs, and (when AI_PROVIDER=codex) manage
/// the Codex login.
Future<void> showSettingsDialog(BuildContext context) async {
  await showDialog(context: context, builder: (context) => const _SettingsDialog());
}

class _SettingsDialog extends StatefulWidget {
  const _SettingsDialog();

  @override
  State<_SettingsDialog> createState() => _SettingsDialogState();
}

class _SettingsDialogState extends State<_SettingsDialog> {
  final _api = ApiClient();

  bool _restarting = false;
  String? _restartError;

  String? _aiProvider;
  bool? _codexLoggedIn;
  String? _codexDetail;
  bool _codexBusy = false;
  String? _codexError;
  Map<String, String>? _loginPrompt; // {"url": ..., "code": ...}

  bool _installing = false;
  final List<String> _installLog = [];

  @override
  void initState() {
    super.initState();
    _refreshCodexStatus();
  }

  bool get _codexMissing => _codexLoggedIn == false && (_codexDetail ?? '').toLowerCase().contains('not found');

  Future<void> _refreshCodexStatus() async {
    try {
      final status = await _api.getCodexStatus();
      if (!mounted) return;
      setState(() {
        _aiProvider = status['ai_provider'] as String?;
        _codexLoggedIn = status['logged_in'] as bool?;
        _codexDetail = status['detail'] as String?;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _codexError = e.toString());
    }
  }

  Future<void> _restart() async {
    setState(() {
      _restarting = true;
      _restartError = null;
    });
    try {
      final old = ApiConfig.handle;
      if (old != null) await BackendLauncher.shutdown(old);
      final fresh = await BackendLauncher.start(devFlag: false);
      ApiConfig.configure(fresh);
      AppLogger.log('Backend restarted at ${fresh.baseUrl}');
      await _refreshCodexStatus();
    } catch (e) {
      _restartError = e.toString();
    } finally {
      if (mounted) setState(() => _restarting = false);
    }
  }

  void _copy(String text, String what) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$what copied')));
  }

  Future<void> _loginToCodex() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Log in to Codex?'),
        content: const Text(
          'Starting a new login immediately ends any Codex session that is '
          'currently logged in on this machine, even if you don\'t finish '
          'this one. Continue?',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Continue')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() {
      _codexBusy = true;
      _codexError = null;
      _loginPrompt = null;
    });
    try {
      final res = await _api.loginCodex();
      if (!mounted) return;
      final code = res['code'] as String;
      setState(() => _loginPrompt = {'url': res['url'] as String, 'code': code});
      // The code is what needs pasting into the browser page — put it on the
      // clipboard immediately so it's ready to paste with no extra click.
      Clipboard.setData(ClipboardData(text: code));
    } catch (e) {
      if (!mounted) return;
      setState(() => _codexError = e.toString());
    } finally {
      if (mounted) setState(() => _codexBusy = false);
    }
  }

  Future<bool> _commandExists(String cmd) async {
    try {
      final res = await Process.run('where', [cmd]);
      return res.exitCode == 0;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _runLogged(String exe, List<String> args) async {
    _installLog.add('> $exe ${args.join(' ')}');
    if (mounted) setState(() {});
    try {
      final proc = await Process.start(exe, args, runInShell: true);
      proc.stdout.transform(SystemEncoding().decoder).listen((s) {
        if (s.trim().isEmpty) return;
        _installLog.add(s.trimRight());
        if (mounted) setState(() {});
      });
      proc.stderr.transform(SystemEncoding().decoder).listen((s) {
        if (s.trim().isEmpty) return;
        _installLog.add(s.trimRight());
        if (mounted) setState(() {});
      });
      final code = await proc.exitCode;
      _installLog.add(code == 0 ? '(done)' : '(exited with code $code)');
      if (mounted) setState(() {});
      return code == 0;
    } catch (e) {
      _installLog.add('Could not run $exe: $e');
      if (mounted) setState(() {});
      return false;
    }
  }

  /// Installs Node.js (via winget, if missing) and the Codex CLI (via npm).
  /// Runs the same commands you'd type yourself — this just types them for
  /// you and shows what happened, rather than doing anything invisible.
  Future<void> _installCodex() async {
    setState(() {
      _installing = true;
      _installLog.clear();
      _codexError = null;
    });

    final hasNode = await _commandExists('node');
    if (!hasNode) {
      _installLog.add('Node.js not found — installing with winget (this can take a few minutes)...');
      if (mounted) setState(() {});
      final ok = await _runLogged('winget', [
        'install', '-e', '--id', 'OpenJS.NodeJS.LTS',
        '--accept-package-agreements', '--accept-source-agreements',
      ]);
      if (!ok) {
        _installLog.add(
          'Automatic Node.js install failed. Install it yourself from nodejs.org '
          '(the LTS version), then press "Install Codex CLI" again.',
        );
        if (mounted) setState(() => _installing = false);
        return;
      }
      _installLog.add('Node.js installed. You may need to restart this app once for PATH changes to take effect.');
    } else {
      _installLog.add('Node.js already installed.');
    }

    _installLog.add('Installing the Codex CLI with npm...');
    if (mounted) setState(() {});
    final npmOk = await _runLogged('npm', ['install', '-g', '@openai/codex']);
    if (!npmOk) {
      _installLog.add(
        'npm install failed. If you just installed Node.js, close and reopen this app '
        'so it picks up the new PATH, then try again.',
      );
    } else {
      _installLog.add('Codex CLI installed.');
    }

    if (mounted) setState(() => _installing = false);
    await _refreshCodexStatus();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Settings'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Backend connection', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              _row('URL', ApiConfig.baseUrl),
              _row('Backend PID', '${ApiConfig.pid ?? "dev mode (not spawned by this app)"}'),
              _row('Log folder', AppLogger.logDir),
              if (_restartError != null) ...[
                const SizedBox(height: 8),
                Text('Restart failed: $_restartError', style: const TextStyle(color: AppColors.accentRed, fontSize: 12)),
              ],
              const Divider(height: 32),
              Text('AI provider', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 4),
              _row('Provider', _aiProvider ?? '…'),
              if (_aiProvider == 'codex') ...[
                if (_codexMissing)
                  _CodexSetupCard(
                    installing: _installing,
                    log: _installLog,
                    onInstall: _installCodex,
                  )
                else ...[
                  _row(
                    'Login',
                    _codexLoggedIn == null ? '…' : (_codexLoggedIn! ? 'Logged in' : 'Not logged in'),
                  ),
                  if (_codexDetail != null && _codexDetail!.isNotEmpty) _row('Detail', _codexDetail!),
                  if (_codexError != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(_codexError!, style: const TextStyle(color: AppColors.accentRed, fontSize: 12)),
                    ),
                  if (_loginPrompt != null) ...[
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: AppColors.panelBgAlt,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('1. Open this link:', style: TextStyle(fontWeight: FontWeight.bold)),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Expanded(child: SelectableText(_loginPrompt!['url']!, style: telemetryStyle(size: 12))),
                              IconButton(
                                icon: const Icon(Icons.copy, size: 16),
                                tooltip: 'Copy link',
                                onPressed: () => _copy(_loginPrompt!['url']!, 'Link'),
                              ),
                              IconButton(
                                icon: const Icon(Icons.open_in_new, size: 16),
                                tooltip: 'Open in browser',
                                onPressed: () => launchUrl(Uri.parse(_loginPrompt!['url']!), mode: LaunchMode.externalApplication),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          const Text('2. Paste this code (already on your clipboard):', style: TextStyle(fontWeight: FontWeight.bold)),
                          const SizedBox(height: 6),
                          Row(
                            children: [
                              Expanded(
                                child: SelectableText(
                                  _loginPrompt!['code']!,
                                  style: const TextStyle(fontFamily: consoleFont, fontSize: 18, fontWeight: FontWeight.w700),
                                ),
                              ),
                              IconButton(
                                icon: const Icon(Icons.copy, size: 16),
                                tooltip: 'Copy code',
                                onPressed: () => _copy(_loginPrompt!['code']!, 'Code'),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      OutlinedButton.icon(
                        onPressed: _codexBusy ? null : _loginToCodex,
                        icon: _codexBusy
                            ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.login, size: 16),
                        label: const Text('Login to Codex'),
                      ),
                      const SizedBox(width: 8),
                      TextButton.icon(
                        onPressed: _refreshCodexStatus,
                        icon: const Icon(Icons.refresh, size: 16),
                        label: const Text('Refresh'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _TroubleshootingNote(),
                ],
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton.icon(
          onPressed: () => Process.run('explorer.exe', [AppLogger.logDir]),
          icon: const Icon(Icons.folder_open, size: 18),
          label: const Text('Open log folder'),
        ),
        TextButton.icon(
          onPressed: _restarting ? null : _restart,
          icon: _restarting
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.restart_alt, size: 18),
          label: const Text('Restart backend'),
        ),
        FilledButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Close')),
      ],
    );
  }
}

class _CodexSetupCard extends StatelessWidget {
  final bool installing;
  final List<String> log;
  final VoidCallback onInstall;

  const _CodexSetupCard({required this.installing, required this.log, required this.onInstall});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.accentAmber.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.accentAmber.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text("Codex isn't installed yet", style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text(
            'Codex is a command-line tool this app shells out to for writing scripts. '
            'It needs Node.js first. The button below installs both — same commands '
            'you\'d type in a terminal, just done for you.',
            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: installing ? null : onInstall,
              icon: installing
                  ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.onAmber))
                  : const Icon(Icons.download, size: 16),
              label: Text(installing ? 'Installing…' : 'Install Node.js + Codex CLI'),
            ),
          ),
          if (log.isNotEmpty) ...[
            const SizedBox(height: 10),
            Container(
              constraints: const BoxConstraints(maxHeight: 160),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: AppColors.panelBgAlt, borderRadius: BorderRadius.circular(8)),
              child: SingleChildScrollView(
                reverse: true,
                child: SelectableText(log.join('\n'), style: telemetryStyle(size: 11)),
              ),
            ),
          ],
          const SizedBox(height: 8),
          const Text(
            "If this doesn't work on your machine: install Node.js from nodejs.org, "
            'then run "npm install -g @openai/codex" yourself in a terminal.',
            style: TextStyle(color: AppColors.textMuted, fontSize: 11),
          ),
        ],
      ),
    );
  }
}

class _TroubleshootingNote extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('Logged in, but still not working?', style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
        childrenPadding: const EdgeInsets.only(bottom: 8),
        children: const [
          Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'That usually isn\'t this app — it\'s a setting on your OpenAI account. '
              'Go to chatgpt.com, open your account Settings (click your name/avatar), '
              'and look for a "Codex" or developer-access option that needs to be turned on. '
              'It lives in ChatGPT\'s own settings, not here.',
              style: TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
          ),
        ],
      ),
    );
  }
}

Widget _row(String label, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 100, child: Text(label, style: const TextStyle(color: AppColors.textMuted))),
          Expanded(child: SelectableText(value, style: const TextStyle(fontFamily: consoleFont, fontSize: 12))),
        ],
      ),
    );
