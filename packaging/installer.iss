; GhostRec installer (Inno Setup 6). Built by packaging/build.py:
;   ISCC /DMyAppVersion=1.3.0 /DSourceDir=dist\GhostRec /DOutputDir=dist installer.iss
; Per-user install: no admin prompt, lands in %LOCALAPPDATA%\Programs\GhostRec.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\GhostRec"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{6B1F3C2E-8E4D-4C1B-9A57-2F6D0B9E7A41}
AppName=GhostRec
AppVersion={#MyAppVersion}
AppVerName=GhostRec {#MyAppVersion}
AppPublisher=jaeef
AppPublisherURL=https://github.com/jaeef/ghostrecord-obs
AppSupportURL=https://github.com/jaeef/ghostrecord-obs/issues
DefaultDirName={autopf}\GhostRec
DefaultGroupName=GhostRec
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutputDir}
OutputBaseFilename=GhostRec-Setup-{#MyAppVersion}
SetupIconFile={#SourceDir}\..\..\ghostrec\ui\assets\app.ico
UninstallDisplayIcon={app}\GhostRec.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\GhostRec"; Filename: "{app}\GhostRec.exe"; AppUserModelID: "GhostRec.OBS"
Name: "{autodesktop}\GhostRec"; Filename: "{app}\GhostRec.exe"; AppUserModelID: "GhostRec.OBS"; Tasks: desktopicon

[Run]
Filename: "{app}\GhostRec.exe"; Description: "Launch GhostRec"; Flags: nowait postinstall skipifsilent

; Settings in %APPDATA%\GhostRec and recordings in Videos\GhostRec are the
; user's data and are intentionally kept on uninstall.
