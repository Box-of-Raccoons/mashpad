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

# The piano-melody notes are gitignored and generated at build time (gen_notes),
# not committed like the voice packs. A build that skipped that step would ship
# the default piano mode with no note clips — fail loudly so it isn't released.
_note_clips = list((REPO / "sounds" / "notes").glob("*.wav"))
if not _note_clips:
    raise SystemExit("mashpad.spec: sounds/notes contains no .wav clips — run `python -m mashpad.gen_notes` before building")

# The effect clips (pops/boings/dings) are also gitignored and generated at
# build time (gen_effects). Without them the dings mode — and the piano->dings
# fallback when notes are missing — have nothing to play; fail loudly so a build
# missing them isn't released.
_effect_clips = list((REPO / "sounds" / "effects").glob("*.wav"))
if not _effect_clips:
    raise SystemExit("mashpad.spec: sounds/effects contains no .wav clips — run `python -m mashpad.gen_effects` before building")

a = Analysis(
    [str(REPO / "packaging" / "launcher.py")],
    pathex=[str(REPO)],
    datas=[
        (str(REPO / "assets"), "assets"),
        (str(REPO / "sounds"), "sounds"),
        (str(REPO / "mashpad"), "mashpad_src"),
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
