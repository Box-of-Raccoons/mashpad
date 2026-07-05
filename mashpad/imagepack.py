# mashpad/imagepack.py — image pack: scans assets/images/ for PNG sticker art.
# Pure — no pygame imports. Loading + scaling happens in main.py.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ImageEntry:
    """Metadata for a single PNG item in the image pack."""
    # File stem (e.g. "raccoon3") — used as item name and as image dict key.
    name: str
    # Absolute path to the PNG file.
    path: Path
    # The spoken word for this image (trailing digits stripped from stem).
    spoken: str


def spoken_word(stem: str) -> str:
    """Return the spoken word for a file stem.

    Strips trailing digits: "raccoon3" → "raccoon", "wave" → "wave".
    If stripping leaves an empty string, returns the original stem as-is
    (e.g. "7" stays "7", "123" stays "123").
    """
    stripped = stem.rstrip("0123456789")
    return stripped if stripped else stem


def scan(directory: Path) -> list[ImageEntry]:
    """Scan *directory* for PNG files and return a sorted ImageEntry list.

    Missing or non-directory *directory* returns an empty list — the app
    must work perfectly with an empty or absent images folder.
    """
    if not directory.is_dir():
        return []
    entries = []
    for path in sorted(directory.glob("*.png")):
        name = path.stem
        entries.append(ImageEntry(name=name, path=path, spoken=spoken_word(name)))
    return entries
