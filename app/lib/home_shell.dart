import 'package:flutter/material.dart';
import 'screens/dashboard_screen.dart';
import 'settings_dialog.dart';
import 'theme.dart';

/// One page. Everything — create, queue, in-progress, finished — lives on
/// Home; Settings (gear icon) is the only other surface, and it's a dialog,
/// not a page.
class HomeShell extends StatelessWidget {
  const HomeShell({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        leading: Padding(
          padding: const EdgeInsets.all(6),
          child: Image.asset('assets/newLogo.png'),
        ),
        title: const Text('Shorts Factory'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () => showSettingsDialog(context),
          ),
          const SizedBox(width: 4),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Container(height: 1, color: AppColors.panelBorder),
        ),
      ),
      body: const DashboardScreen(),
    );
  }
}
