# PyInstaller spec for the mashpad Windows desktop edition (one-dir build:
# faster startup than one-file and far fewer antivirus false positives).
# Built by the orchestrator from the repo worktree; assets/sounds ship inside.
#
#   pyinstaller mashpad.spec --noconfirm --distpath dist
#
# Paths are resolved relative to this spec's location (packaging/ inside the
# repo), so the spec is committed and reproducible.

from pathlib import Path

REPO = Path(SPECPATH).resolve().parent  # SPECPATH IS the packaging dir -> repo root

# A build without the committed voice packs ships a silent app — fail loudly.
_voice_clips = list((REPO / "sounds" / "voice").rglob("*.ogg"))
if not _voice_clips:
    raise SystemExit("mashpad.spec: sounds/voice contains no .ogg clips — voice packs missing from this worktree")

a = Analysis(
    [str(REPO / "packaging" / "launcher.py")],
    pathex=[str(REPO)],
    datas=[
        (str(REPO / "assets"), "assets"),
        (str(REPO / "sounds"), "sounds"),
    ],
    hiddenimports=[],
    excludes=["numpy", "tkinter", "unittest", "pydoc"],  # numpy is gen-tool only
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="mashpad",
    icon=str(REPO / "packaging" / "mashpad.ico"),
    console=False,               # GUI app — no console window
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="mashpad",
)
