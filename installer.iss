; Inno Setup script -> a single AI-YouTube-Video-Generator-Setup.exe.
; Build: iscc installer.iss  (after assembling app\build\windows\x64\runner\Release
; the same way the GitHub release zip is built -- see README "Building the installer").
;
; Installs per-user (PrivilegesRequired=lowest, DefaultDirName under
; {localappdata}) rather than Program Files -- the app writes main.db, logs,
; and rendered videos directly next to its own exe at runtime, and Program
; Files is read-only for standard users without elevation.

#define MyAppName "AI YouTube Video Generator"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "tuvshinorg"
#define MyAppExeName "ytgen_manager.exe"
#define ReleaseDir "app\build\windows\x64\runner\Release"

[Setup]
AppId={{B3B6C8B2-9C9A-4B7E-9E9B-3C9F7C6F5A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=AI-YouTube-Video-Generator-Setup-v{#MyAppVersion}
SetupIconFile=app\windows\runner\resources\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only removes what a fresh, never-run install would contain (Files section
; above) -- main.db, logs/, temp/, final/ (your rendered videos), and .env
; are created after install and are intentionally left behind so
; uninstalling never deletes finished work.
