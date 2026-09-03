import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api_client.dart';
import '../settings_dialog.dart';
import '../stage_ring.dart';
import '../theme.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

// Gradient families derived from the brand palette (robot blue, YouTube red,
// amber trail) — used for finished-video tiles, which have no real thumbnail.
const _tileGradients = [
  [Color(0xFF123A44), Color(0xFF1B5E6E)], // blue-teal
  [Color(0xFF0F3B2E), Color(0xFF1D6B4C)], // green-teal
  [Color(0xFF4A2E0C), Color(0xFF8C5A17)], // amber-brown
  [Color(0xFF3E1414), Color(0xFF7A2320)], // red-maroon
  [Color(0xFF241B44), Color(0xFF3D2E75)], // indigo
];

class _DashboardScreenState extends State<DashboardScreen> {
  final _api = ApiClient();
  final _ideaCtrl = TextEditingController();

  Map<String, dynamic>? _status;
  Map<String, dynamic>? _pipelineStatus;
  Map<String, dynamic>? _queue;
  Map<String, dynamic>? _codexStatus;
  Map<String, dynamic>? _setupStatus;
  bool _setupBusy = false;
  List<dynamic> _videos = [];
  String? _error;
  bool _busy = false;

  WebSocket? _ws;
  StreamSubscription? _wsSub;
  Timer? _pollTimer;
  Timer? _queueTimer;

  @override
  void initState() {
    super.initState();
    _refreshStatusAndQueue();
    _refreshSetupStatus();
    _queueTimer = Timer.periodic(const Duration(seconds: 5), (_) => _refreshStatusAndQueue(silent: true));
    _connectWebSocket();
  }

  // Checked once at launch (not on the 5s poll — it spawns a subprocess to
  // probe installed packages, worth ~1s but not worth paying repeatedly)
  // plus on demand from the banner's "Recheck" button.
  Future<void> _refreshSetupStatus() async {
    setState(() => _setupBusy = true);
    try {
      final setup = await _api.getSetupStatus();
      if (mounted) setState(() => _setupStatus = setup);
    } catch (_) {
      // Best-effort — the existing "cannot reach backend" error screen
      // already covers a backend that isn't up at all.
    } finally {
      if (mounted) setState(() => _setupBusy = false);
    }
  }

  @override
  void dispose() {
    _ideaCtrl.dispose();
    _wsSub?.cancel();
    _ws?.close();
    _pollTimer?.cancel();
    _queueTimer?.cancel();
    super.dispose();
  }

  Future<void> _connectWebSocket() async {
    try {
      final wsUrl = ApiConfig.baseUrl.replaceFirst('http', 'ws');
      final socket = await WebSocket.connect(
        '$wsUrl/ws/pipeline',
        headers: ApiConfig.token.isNotEmpty ? {'Authorization': 'Bearer ${ApiConfig.token}'} : null,
      );
      if (!mounted) {
        socket.close();
        return;
      }
      _pollTimer?.cancel();
      _ws = socket;
      _wsSub = socket.listen(
        (data) {
          if (!mounted) return;
          try {
            setState(() => _pipelineStatus = Map<String, dynamic>.from(jsonDecode(data as String)));
          } catch (_) {}
        },
        onError: (_) => _fallBackToPolling(),
        onDone: () => _fallBackToPolling(),
      );
    } catch (_) {
      _fallBackToPolling();
    }
  }

  void _fallBackToPolling() {
    if (!mounted || _pollTimer != null) return;
    _pollTimer = Timer.periodic(const Duration(milliseconds: 500), (_) async {
      try {
        final s = await _api.getPipelineStatus();
        if (mounted) setState(() => _pipelineStatus = s);
      } catch (_) {}
    });
  }

  Future<void> _refreshStatusAndQueue({bool silent = false}) async {
    if (!silent) setState(() => _error = null);
    try {
      final status = await _api.getStatus();
      final queue = await _api.getQueue();
      if (!mounted) return;
      setState(() {
        _status = status;
        _queue = queue;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    }
    try {
      final videos = await _api.getVideos();
      if (mounted) setState(() => _videos = videos);
    } catch (_) {}
    try {
      final codex = await _api.getCodexStatus();
      if (mounted) setState(() => _codexStatus = codex);
    } catch (_) {}
  }

  Future<void> _makeTheVideo() async {
    final text = _ideaCtrl.text.trim();
    if (text.isEmpty) return;
    setState(() => _busy = true);
    try {
      await _api.addText(text);
      // Always saves the .mp4 locally — YouTube upload needs credentials
      // this app doesn't set up, so that path isn't offered here.
      final res = await _api.runPipeline('file');
      if (!mounted) return;
      final msg = res['ok'] == true ? 'Queued — pipeline started (PID ${res['pid']})' : (res['note'] ?? 'Queued, but could not start the pipeline');
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      _ideaCtrl.clear();
      await _refreshStatusAndQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not queue it: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // Manually nudges the pipeline forward when idle but there's unfinished
  // work sitting in the queue/in-progress — no new text required.
  Future<void> _runNow() async {
    setState(() => _busy = true);
    try {
      final res = await _api.runPipeline('file');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['ok'] == true ? 'Pipeline started (PID ${res['pid']})' : (res['note'] ?? 'Could not start'))),
      );
      await _refreshStatusAndQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _stop() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Stop pipeline?'),
        content: const Text('This force-kills the running pipeline and any ffmpeg processes it started.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Stop')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _busy = true);
    try {
      final res = await _api.stopPipeline();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['ok'] == true ? 'Pipeline stopped' : (res['note'] ?? 'Stop failed'))),
      );
      await _refreshStatusAndQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // "Resume" — clears the error/re-queues it, then immediately starts the
  // pipeline so it actually gets worked on rather than just sitting ready.
  Future<void> _resume(int seedId) async {
    try {
      final res = await _api.retrySeed(seedId);
      if (!mounted) return;
      if (res['ok'] != true) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(res['note'] ?? 'Nothing to resume')));
        return;
      }
      final runRes = await _api.runPipeline('file');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(runRes['ok'] == true ? 'Resumed — pipeline started (PID ${runRes['pid']})' : 'Queued — will run on the next pipeline start')),
      );
      await _refreshStatusAndQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error: $e')));
    }
  }

  Future<void> _open(int seedId) async {
    final url = Uri.parse(_api.videoUrl(seedId));
    final ok = await launchUrl(url, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not open $url')));
    }
  }

  Future<void> _deleteQueueEntry(int queueId) async {
    final confirmed = await _confirmDelete('Delete this queued item? It hasn\'t started processing yet.');
    if (confirmed != true) return;
    try {
      await _api.deleteQueueEntry(queueId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Deleted')));
      await _refreshStatusAndQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not delete: $e')));
    }
  }

  Future<void> _deleteSeed(int seedId, {bool hasVideo = false}) async {
    final confirmed = await _confirmDelete(
      hasVideo
          ? 'Delete this project? Its rendered .mp4 will be deleted too. This can\'t be undone.'
          : 'Delete this project? This can\'t be undone.',
    );
    if (confirmed != true) return;
    try {
      await _api.deleteSeed(seedId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Deleted')));
      await _refreshStatusAndQueue();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not delete: $e')));
    }
  }

  Future<bool?> _confirmDelete(String message) {
    return showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete?'),
        content: Text(message),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.accentRed),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
  }

  Future<void> _openQueueDetail(int queueId) async {
    showDialog(context: context, builder: (context) => _DetailDialog(loader: () => _api.getQueueEntry(queueId)));
  }

  Future<void> _openSeedDetail(int seedId) async {
    showDialog(context: context, builder: (context) => _DetailDialog(loader: () => _api.getSeedDetail(seedId)));
  }

  String _formatSize(int bytes) {
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  List<dynamic> get _finishedToday {
    final today = DateTime.now().toIso8601String().substring(0, 10);
    return _videos.where((v) => (v['modified'] as String? ?? '').startsWith(today)).toList();
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null && _status == null) {
      return RefreshIndicator(
        onRefresh: _refreshStatusAndQueue,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 48),
            const Icon(Icons.cloud_off, size: 40, color: AppColors.textMuted),
            const SizedBox(height: 12),
            const Text('Cannot reach the backend', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 8),
            Text(_error!, style: telemetryStyle()),
            const SizedBox(height: 16),
            Center(child: FilledButton(onPressed: _refreshStatusAndQueue, child: const Text('Retry'))),
          ],
        ),
      );
    }

    final running = (_pipelineStatus?['running'] ?? _status?['running']) == true;
    final pid = _pipelineStatus?['pid'] ?? _status?['pid'];
    final stage = _pipelineStatus?['stage'] as String?;
    final percent = _pipelineStatus?['percent'] as int?;
    final message = _pipelineStatus?['message'] as String?;
    final startedAt = _pipelineStatus?['started_at'] as String?;
    final logTail = ((_pipelineStatus?['log_tail'] as List?) ?? []).cast<String>();
    final pending = (_queue?['queue_pending'] as List?) ?? [];
    final seeds = (_queue?['seeds'] as List?) ?? [];
    final errored = seeds.where((s) => s['stage'] == 'error').toList();
    // A seed whose .mp4 already exists (i.e. it's in _videos) is done, full
    // stop — but its DB stage sits at 'rendered' forever, since "Make the
    // video" always runs the pipeline with output=file and no YouTube
    // upload ever happens to set seedUploadStamp. Without this check every
    // finished project would show under both "In progress" and "Finished"
    // permanently, not just transiently.
    final finishedSeedIds = _videos.map((v) => v['seed_id']).whereType<int>().toSet();
    final inProgress = seeds
        .where((s) => s['stage'] != 'error' && s['stage'] != 'uploaded' && !finishedSeedIds.contains(s['seedId']))
        .toList();
    final codexNotLoggedIn = _codexStatus?['ai_provider'] == 'codex' && _codexStatus?['logged_in'] == false;
    // null while the check is still in flight — don't flash the banner
    // before we actually know.
    final packagesNotReady = _setupStatus != null && _setupStatus?['packages_ready'] == false;
    final baseDir = _status?['base_dir'] as String?;
    final finishedToday = _finishedToday;

    return RefreshIndicator(
      onRefresh: _refreshStatusAndQueue,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              TelemetryPill(
                dotColor: running ? AppColors.accentAmber : AppColors.textMuted,
                label: running ? 'pipeline running${pid != null ? ' · pid $pid' : ''}' : 'pipeline idle',
              ),
              const SizedBox(width: 16),
              TelemetryPill(dotColor: AppColors.accentBlue, label: '${pending.length} waiting'),
              const SizedBox(width: 16),
              TelemetryPill(dotColor: errored.isNotEmpty ? AppColors.accentRed : AppColors.textMuted, label: '${errored.length} errors'),
            ],
          ),
          const SizedBox(height: 16),
          if (packagesNotReady) ...[
            Card(
              color: AppColors.accentRed.withValues(alpha: 0.10),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.warning_amber, color: AppColors.accentRed),
                        const SizedBox(width: 10),
                        const Expanded(
                          child: Text("Python dependencies aren't installed yet", style: TextStyle(fontWeight: FontWeight.w700)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    const Text(
                      'The pipeline (image/voice/subtitle generation) needs these before anything will work. Run this once:',
                      style: TextStyle(color: AppColors.textMuted, fontSize: 12),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(color: AppColors.panelBgAlt, borderRadius: BorderRadius.circular(8)),
                      child: Row(
                        children: [
                          Expanded(child: SelectableText('pip install -r requirements.txt', style: consoleStyle(size: 12))),
                          IconButton(
                            icon: const Icon(Icons.copy, size: 16),
                            tooltip: 'Copy command',
                            onPressed: () {
                              Clipboard.setData(const ClipboardData(text: 'pip install -r requirements.txt'));
                              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Command copied')));
                            },
                          ),
                        ],
                      ),
                    ),
                    if (baseDir != null) ...[
                      const SizedBox(height: 6),
                      Text('Run it from: $baseDir', style: telemetryStyle(size: 11)),
                    ],
                    const SizedBox(height: 10),
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        onPressed: _setupBusy ? null : _refreshSetupStatus,
                        icon: _setupBusy
                            ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                            : const Icon(Icons.refresh, size: 16),
                        label: const Text("I've installed it — Recheck"),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
          if (codexNotLoggedIn) ...[
            Card(
              color: AppColors.accentRed.withValues(alpha: 0.10),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: const BorderSide(color: AppColors.accentRed),
              ),
              child: ListTile(
                leading: const Icon(Icons.warning_amber, color: AppColors.accentRed),
                title: const Text('Codex is not logged in', style: TextStyle(fontWeight: FontWeight.w700)),
                subtitle: const Text('Text/scene generation will fail until you sign in.', style: TextStyle(color: AppColors.textMuted)),
                trailing: FilledButton(
                  onPressed: () => showSettingsDialog(context).then((_) => _refreshStatusAndQueue()),
                  child: const Text('Log in'),
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
          LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth > 760;
              final create = _CreatePanel(
                controller: _ideaCtrl,
                busy: _busy,
                onSubmit: _makeTheVideo,
                finishedToday: finishedToday,
              );
              final status = _StatusPanel(
                running: running,
                stage: stage,
                percent: percent,
                message: message,
                startedAt: startedAt,
                logTail: logTail,
                onStop: running ? _stop : null,
                busy: _busy,
                pendingCount: pending.length,
                inProgressCount: inProgress.length,
                erroredCount: errored.length,
                onRunNow: _runNow,
              );
              if (!wide) {
                return Column(children: [create, const SizedBox(height: 12), status]);
              }
              return IntrinsicHeight(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(flex: 3, child: create),
                    const SizedBox(width: 12),
                    Expanded(flex: 2, child: status),
                  ],
                ),
              );
            },
          ),
          const Divider(),
          if (errored.isNotEmpty) ...[
            _SectionHeader('Needs attention', errored.length),
            _groupedList(errored.map((s) {
              final seedId = s['seedId'] as int;
              return ListTile(
                onTap: () => _openSeedDetail(seedId),
                leading: StageRing(
                  size: 34,
                  color: AppColors.accentRed,
                  value: 1,
                  child: const Icon(Icons.priority_high_rounded, color: AppColors.accentRed, size: 15),
                ),
                title: Text(s['seedTitle'] ?? '(untitled)'),
                subtitle: Text('Failed at ${s['seedErrorStep']} — ${s['seedErrorMsg'] ?? ''}',
                    style: telemetryStyle(color: const Color(0xFFFF8079)), maxLines: 2, overflow: TextOverflow.ellipsis),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextButton(onPressed: () => _resume(seedId), child: const Text('Resume')),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 20),
                      tooltip: 'Delete',
                      onPressed: () => _deleteSeed(seedId),
                    ),
                  ],
                ),
              );
            }).toList()),
            const SizedBox(height: 8),
          ],
          if (pending.isNotEmpty) ...[
            _SectionHeader('Waiting to be processed', pending.length),
            _groupedList(pending.map((r) {
              final queueId = r['queueId'] as int;
              return ListTile(
                onTap: () => _openQueueDetail(queueId),
                leading: StageRing(
                  size: 34,
                  color: AppColors.textMuted,
                  value: 0,
                  child: const Icon(Icons.article_outlined, color: AppColors.textMuted, size: 15),
                ),
                title: Text((r['snippet'] ?? '').toString().replaceAll('\n', ' '), maxLines: 2, overflow: TextOverflow.ellipsis),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('#$queueId', style: telemetryStyle()),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 20),
                      tooltip: 'Delete',
                      onPressed: () => _deleteQueueEntry(queueId),
                    ),
                  ],
                ),
              );
            }).toList()),
            const SizedBox(height: 8),
          ],
          if (inProgress.isNotEmpty) ...[
            _SectionHeader('In progress', inProgress.length),
            _groupedList(inProgress.map((s) {
              final seedId = s['seedId'] as int;
              final stg = s['stage'] as String? ?? 'processing';
              final color = stageColor(stg);
              return ListTile(
                onTap: () => _openSeedDetail(seedId),
                leading: StageRing(
                  size: 34,
                  color: color,
                  value: stageProgress(stg),
                  child: Icon(Icons.movie_outlined, color: color, size: 15),
                ),
                title: Text(s['seedTitle'] ?? '(untitled)'),
                subtitle: Text('$stg · ${s['seedCreatedDate'] ?? ''}', style: telemetryStyle()),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline, size: 20),
                  tooltip: 'Delete',
                  onPressed: () => _deleteSeed(seedId),
                ),
              );
            }).toList()),
            const SizedBox(height: 8),
          ],
          if (_videos.isNotEmpty) ...[
            _SectionHeader('Finished', _videos.length),
            _groupedList(_videos.map((v) {
              final seedId = v['seed_id'] as int?;
              final uploaded = v['uploaded'] == true;
              // A finished local file is a real success state even when it
              // was never uploaded (this app's "Make the video" flow never
              // uploads at all — see the inProgress filter above) — so the
              // ring is always full, just tinted by whether it shipped.
              final color = uploaded ? AppColors.accentGreen : AppColors.accentBlue;
              return ListTile(
                onTap: seedId == null ? null : () => _openSeedDetail(seedId),
                leading: StageRing(
                  size: 34,
                  color: color,
                  value: 1,
                  child: Icon(uploaded ? Icons.cloud_done_outlined : Icons.check_rounded, color: color, size: 16),
                ),
                title: Text(v['title'] ?? v['filename'] ?? ''),
                subtitle: Text('${_formatSize(v['size_bytes'] ?? 0)} · ${v['modified'] ?? ''}', style: telemetryStyle()),
                trailing: seedId == null
                    ? null
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            icon: const Icon(Icons.play_circle_outline),
                            tooltip: 'Open / download',
                            onPressed: () => _open(seedId),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete_outline, size: 20),
                            tooltip: 'Delete',
                            onPressed: () => _deleteSeed(seedId, hasVideo: true),
                          ),
                        ],
                      ),
              );
            }).toList()),
          ],
          if (errored.isEmpty && pending.isEmpty && inProgress.isEmpty && _videos.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 24),
              child: Center(
                child: Text('Nothing here yet. Write an idea above to start your first project.',
                    style: TextStyle(color: AppColors.textMuted), textAlign: TextAlign.center),
              ),
            ),
        ],
      ),
    );
  }
}

/// "Look inside" — fetches and shows either a queued entry's full text or a
/// project's title/description/scene breakdown, depending on what the
/// loader returns.
class _DetailDialog extends StatefulWidget {
  final Future<Map<String, dynamic>> Function() loader;
  const _DetailDialog({required this.loader});

  @override
  State<_DetailDialog> createState() => _DetailDialogState();
}

class _DetailDialogState extends State<_DetailDialog> {
  Map<String, dynamic>? _data;
  String? _error;

  @override
  void initState() {
    super.initState();
    widget.loader().then(
      (d) => mounted ? setState(() => _data = d) : null,
      onError: (e) => mounted ? setState(() => _error = e.toString()) : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final isSeed = _data?.containsKey('scenes') == true;
    return AlertDialog(
      title: Text(isSeed ? (_data!['seedTitle'] as String? ?? 'Untitled') : 'Queued text'),
      content: SizedBox(
        width: 480,
        child: _error != null
            ? Text(_error!, style: const TextStyle(color: AppColors.accentRed))
            : _data == null
                ? const SizedBox(height: 80, child: Center(child: CircularProgressIndicator()))
                : SingleChildScrollView(
                    child: isSeed ? _seedContent(_data!) : _queueContent(_data!),
                  ),
      ),
      actions: [FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
    );
  }

  Widget _queueContent(Map<String, dynamic> d) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Group: ${d['queueGroup'] ?? ''} · Queued: ${d['queueStamp'] ?? ''}', style: telemetryStyle()),
        const SizedBox(height: 12),
        SelectableText(d['queueText'] as String? ?? ''),
      ],
    );
  }

  Widget _seedContent(Map<String, dynamic> d) {
    final scenes = (d['scenes'] as List?) ?? [];
    final stage = d['stage'] as String? ?? 'processing';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TelemetryPill(dotColor: stageColor(stage), label: stage),
        if ((d['seedDescription'] as String?)?.isNotEmpty == true && d['seedDescription'] != 'not loaded') ...[
          const SizedBox(height: 10),
          SelectableText(d['seedDescription'] as String),
        ],
        if (stage == 'error') ...[
          const SizedBox(height: 10),
          Text('Failed at: ${d['seedErrorStep']}', style: const TextStyle(color: AppColors.accentRed, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          SelectableText(d['seedErrorMsg'] as String? ?? '', style: const TextStyle(color: AppColors.accentRed, fontSize: 12)),
        ],
        if (scenes.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('Scenes', style: TextStyle(fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          ...scenes.map((s) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Scene ${s['sceneNumber']}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
                    const SizedBox(height: 2),
                    SelectableText(s['sceneText'] as String? ?? '', style: const TextStyle(fontSize: 13)),
                    const SizedBox(height: 2),
                    Text('Image: ${s['sceneImage'] ?? ''}', style: telemetryStyle(size: 11)),
                  ],
                ),
              )),
        ],
      ],
    );
  }
}

// A quiet uppercase eyebrow — macOS System Settings' section-label style —
// instead of a bold colored-dot header. The color already lives on each
// row's StageRing; repeating it in the header was noise.
class _SectionHeader extends StatelessWidget {
  final String label;
  final int count;

  const _SectionHeader(this.label, this.count);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10, top: 6, left: 2),
      child: Row(
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 11.5, letterSpacing: 0.7, color: AppColors.textMuted),
          ),
          const SizedBox(width: 6),
          Text('$count', style: telemetryStyle()),
        ],
      ),
    );
  }
}

/// macOS-style "grouped inset list" — one rounded container per section,
/// rows separated by hairline dividers instead of each row being its own
/// bordered Card. This is the single biggest lever on how "considered" the
/// list looks: fewer, quieter boundaries instead of one stroke per row.
Widget _groupedList(List<Widget> rows) {
  final children = <Widget>[];
  for (var i = 0; i < rows.length; i++) {
    children.add(rows[i]);
    if (i != rows.length - 1) {
      children.add(const Divider(height: 1, thickness: 1, indent: 66));
    }
  }
  return Container(
    margin: const EdgeInsets.only(bottom: 8),
    decoration: BoxDecoration(color: AppColors.panelBg, borderRadius: BorderRadius.circular(16)),
    clipBehavior: Clip.antiAlias,
    child: Column(children: children),
  );
}

class _CreatePanel extends StatelessWidget {
  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSubmit;
  final List<dynamic> finishedToday;

  const _CreatePanel({
    required this.controller,
    required this.busy,
    required this.onSubmit,
    required this.finishedToday,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Paste an article, or write your idea. The rest is automatic.',
                style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              maxLines: 8,
              minLines: 6,
              decoration: const InputDecoration(hintText: 'Scientists in Iceland drilled into a magma chamber and...'),
            ),
            const SizedBox(height: 6),
            AnimatedBuilder(
              animation: controller,
              builder: (context, _) => Align(
                alignment: Alignment.centerRight,
                child: Text('${controller.text.length} characters · 6 scenes', style: telemetryStyle()),
              ),
            ),
            const SizedBox(height: 14),
            AnimatedBuilder(
              animation: controller,
              builder: (context, _) => SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: busy || controller.text.trim().isEmpty ? null : onSubmit,
                  child: busy
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.onAmber))
                      : const Text('Make the video'),
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text('Finished today', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 10),
            if (finishedToday.isEmpty)
              const Text('Nothing finished yet today.', style: TextStyle(color: AppColors.textMuted, fontSize: 12))
            else
              SizedBox(
                height: 96,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: finishedToday.length,
                  separatorBuilder: (context, i) => const SizedBox(width: 10),
                  itemBuilder: (context, i) => _FinishedTile(video: finishedToday[i]),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _FinishedTile extends StatelessWidget {
  final dynamic video;
  const _FinishedTile({required this.video});

  @override
  Widget build(BuildContext context) {
    final seedId = video['seed_id'] as int? ?? 0;
    final title = (video['title'] as String? ?? 'Untitled').trim();
    final uploaded = video['uploaded'] == true;
    final grad = _tileGradients[seedId.abs() % _tileGradients.length];

    return Container(
      width: 68,
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: grad, begin: Alignment.topLeft, end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(uploaded ? Icons.cloud_done_outlined : Icons.save_alt, size: 14, color: Colors.white70),
          const Spacer(),
          Text(
            title,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 10, color: Colors.white, fontWeight: FontWeight.w600, height: 1.2),
          ),
        ],
      ),
    );
  }
}

class _StatusPanel extends StatelessWidget {
  final bool running;
  final String? stage;
  final int? percent;
  final String? message;
  final String? startedAt;
  final List<String> logTail;
  final VoidCallback? onStop;
  final bool busy;
  final int pendingCount;
  final int inProgressCount;
  final int erroredCount;
  final VoidCallback? onRunNow;

  const _StatusPanel({
    required this.running,
    this.stage,
    this.percent,
    this.message,
    this.startedAt,
    this.logTail = const [],
    this.onStop,
    required this.busy,
    this.pendingCount = 0,
    this.inProgressCount = 0,
    this.erroredCount = 0,
    this.onRunNow,
  });

  String? get _elapsed {
    if (startedAt == null) return null;
    try {
      final d = DateTime.now().difference(DateTime.parse(startedAt!));
      if (d.inSeconds < 60) return 'running ${d.inSeconds}s';
      final m = d.inMinutes;
      final s = d.inSeconds % 60;
      return 'running ${m}m ${s}s';
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: running ? _buildRunning(context) : _buildIdle(context),
      ),
    );
  }

  Widget _buildRunning(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        StageRing(
          size: 96,
          strokeWidth: 5,
          color: AppColors.accentAmber,
          // percent only advances between stages, not within one — a real
          // stage can sit at the same percent for tens of seconds. Show
          // indeterminate motion instead of a static fraction so "working"
          // never reads as "stuck".
          value: percent == null || percent == 0 ? null : percent! / 100,
          child: const Icon(Icons.movie_creation_outlined, size: 26, color: AppColors.accentAmber),
        ),
        const SizedBox(height: 14),
        Text(stage ?? 'working', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        if (_elapsed != null) ...[
          const SizedBox(height: 2),
          Text(_elapsed!, style: telemetryStyle()),
        ],
        if (message != null) ...[
          const SizedBox(height: 6),
          Text(message!, style: telemetryStyle(), textAlign: TextAlign.center),
        ],
        const SizedBox(height: 18),
        Align(
          alignment: Alignment.centerLeft,
          child: Text('ACTIVITY', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 10.5, letterSpacing: 0.7, color: AppColors.textMuted)),
        ),
        const SizedBox(height: 6),
        Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: 90, maxHeight: 140),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: AppColors.panelBgAlt, borderRadius: BorderRadius.circular(10)),
          child: logTail.isEmpty
              ? Text('Waiting for the first log line…', style: consoleStyle(size: 11))
              : SingleChildScrollView(
                  reverse: true,
                  child: SelectableText(logTail.join('\n'), style: consoleStyle(size: 11)),
                ),
        ),
        const SizedBox(height: 14),
        TextButton.icon(
          onPressed: busy ? null : onStop,
          icon: const Icon(Icons.stop_circle, color: AppColors.accentRed, size: 18),
          label: const Text('Stop pipeline', style: TextStyle(color: AppColors.accentRed)),
        ),
      ],
    );
  }

  Widget _buildIdle(BuildContext context) {
    final unfinished = pendingCount + inProgressCount + erroredCount;
    if (unfinished == 0) {
      return Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const StageRing(
            size: 96,
            strokeWidth: 5,
            color: AppColors.textMuted,
            value: 0,
            child: Icon(Icons.check_rounded, size: 26, color: AppColors.textMuted),
          ),
          const SizedBox(height: 16),
          const Text('Nothing rendering yet', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
          const SizedBox(height: 8),
          const Text(
            'Queue an idea above — it shows up here while it renders, vertical and ready to post.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
        ],
      );
    }
    // Idle doesn't mean empty — say exactly what's sitting here and why
    // nothing is moving, instead of a generic message that contradicts
    // the sections below it.
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const StageRing(
          size: 96,
          strokeWidth: 5,
          color: AppColors.accentAmber,
          value: 0,
          child: Icon(Icons.pause_rounded, size: 26, color: AppColors.accentAmber),
        ),
        const SizedBox(height: 16),
        const Text('Pipeline is idle', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        const SizedBox(height: 8),
        Text(
          [
            if (erroredCount > 0) '$erroredCount needing attention',
            if (pendingCount > 0) '$pendingCount waiting',
            if (inProgressCount > 0) '$inProgressCount in progress',
          ].join(' · '),
          textAlign: TextAlign.center,
          style: telemetryStyle(),
        ),
        const SizedBox(height: 4),
        const Text(
          "Nothing is running right now — it won't move until the pipeline starts again.",
          textAlign: TextAlign.center,
          style: TextStyle(color: AppColors.textMuted, fontSize: 12),
        ),
        const SizedBox(height: 14),
        FilledButton.icon(
          onPressed: busy ? null : onRunNow,
          icon: const Icon(Icons.play_arrow, size: 18),
          label: const Text('Run now'),
        ),
      ],
    );
  }
}
