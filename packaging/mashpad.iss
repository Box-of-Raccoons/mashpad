; Inno Setup script for the mashpad Windows installer.
; Compile (after the PyInstaller one-dir build lands in packaging\dist\mashpad):
;   iscc mashpad.iss
; Produces packaging\out\mashpad-setup-<version>.exe

#define AppName "mashpad"
#define AppVersion "1.1.0"
#define Company "Box of Raccoons LLC"

[Setup]
AppId={{7E1FA9D3-52B8-4C1E-9D0B-6C6B3A9BD0F1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Company}
AppPublisherURL=https://github.com/Box-of-Raccoons/mashpad
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no UAC prompt, lands under %LOCALAPPDATA%Programs.
PrivilegesRequired=lowest
OutputDir=out
OutputBaseFilename=mashpad-setup-{#AppVersion}
SetupIconFile=mashpad.ico
UninstallDisplayIcon={app}\mashpad.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\mashpad\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\mashpad.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\mashpad.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\mashpad.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; settings live in %APPDATA%\mashpad — leave them unless the user removes them
