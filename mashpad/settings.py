# mashpad/settings.py — grown-up options persisted to a JSON file.
#
# Pure — no pygame imports (joins the purity test). menu.py / main.py own all
# UI and audio; this module is only load / save + field-wise validation. The
# caller passes the settings-file Path (settings.py never touches the mixer or
# guesses the repo root).

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# Volume is an integer percentage; the menu steps it by 10.
VOLUME_MIN = 0
VOLUME_MAX = 100
# The only accepted values for the two enum-like fields.
LETTER_CASES = ("upper", "lower")
RACCOON_AMOUNTS = ("less", "normal", "lots")
# Voice-mode selection constants.
VOICE_MODE_RANDOM = "random"
VOICE_MODE_CYCLE = "cycle"


@dataclass
class Settings:
    """The four grown-up-tunable options, with baby-safe defaults."""
    # VOICE_MODE_RANDOM | VOICE_MODE_CYCLE | a specific voice-pack name.
    voice_mode: str = VOICE_MODE_RANDOM
    # Master volume 0–100 (UI steps by 10).
    volume: int = 80
    # "upper" → letters render as A-Z; "lower" → a-z.
    letter_case: str = "upper"
    # "less" | "normal" | "lots" — how often non-letter keys spawn image art.
    raccoon_amount: str = "normal"
    # Whether the app occasionally speaks a reactive phrase (e.g. "slow down!").
    phrases: bool = True


def _from_dict(raw: dict) -> Settings:
    """Build Settings from a decoded JSON dict, defaulting each invalid field.

    Field-wise: a bad value for one key never discards the valid siblings.
    """
    s = Settings()

    vm = raw.get("voice_mode")
    # Any non-empty string is a valid mode ("random"/"cycle"/a voice name);
    # settings.py can't know the live voice list, so it only checks the type.
    if isinstance(vm, str) and vm:
        s.voice_mode = vm

    vol = raw.get("volume")
    # bool is a subclass of int — reject it explicitly (JSON true/false).
    if isinstance(vol, int) and not isinstance(vol, bool) and VOLUME_MIN <= vol <= VOLUME_MAX:
        s.volume = vol

    lc = raw.get("letter_case")
    if lc in LETTER_CASES:
        s.letter_case = lc

    ra = raw.get("raccoon_amount")
    if ra in RACCOON_AMOUNTS:
        s.raccoon_amount = ra

    ph = raw.get("phrases")
    # Strict bool only — reject ints/strings (JSON true/false decode to bool).
    if isinstance(ph, bool):
        s.phrases = ph

    return s


def load(path: Path) -> Settings:
    """Load settings from *path*. Missing file / bad JSON / non-object → defaults.

    Individual invalid fields fall back to their defaults (see _from_dict).
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(raw, dict):
        return Settings()
    return _from_dict(raw)


def save(settings: Settings, path: Path) -> bool:
    """Write *settings* to *path* atomically (tmp → fsync → os.replace).

    Returns True on success, False on OSError (e.g. SD card read-only or full).
    On failure a single warning line is printed; the app continues normally.
    """
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    data = {
        "voice_mode": settings.voice_mode,
        "volume": settings.volume,
        "letter_case": settings.letter_case,
        "raccoon_amount": settings.raccoon_amount,
        "phrases": settings.phrases,
    }
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)  # atomic on the same filesystem
    except OSError as exc:
        print(f"[mashpad settings] could not save {path}: {exc}")
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True
