# packaging — Windows desktop edition

Build the installer (dev machine, from this directory):

```powershell
pip install pyinstaller
python -m PyInstaller mashpad.spec --noconfirm     # one-dir bundle -> dist/mashpad/
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" mashpad.iss   # -> out/mashpad-setup-<ver>.exe
```

- One-dir (not one-file): faster startup, fewer antivirus false positives.
- `mashpad.ico` is derived from `assets/splash.png` (tools/README.md pipeline).
- Installer is per-user (`PrivilegesRequired=lowest`): no admin/UAC, installs to
  `%LOCALAPPDATA%\Programs\mashpad`, Start-menu + optional desktop shortcut.
- Settings live in `%APPDATA%\mashpad\settings.json` (survive reinstalls;
  uninstall leaves them).
- Bump `AppVersion` in `mashpad.iss` at release (matches the stripped
  `mashpad.__version__`).
- Voice packs: whatever `sounds/voice/` packs exist at build time ship inside
  the bundle. Rebuild after regenerating audio.
- Keyboard lockdown (fullscreen only): swallows Win key / Alt-Tab / Alt-F4 /
  Alt-Esc / Ctrl-Esc; Ctrl+Alt+Del is OS-reserved and stays. `--no-lockdown`
  disables. macOS edition: not started — needs Mac hardware to build/verify.
