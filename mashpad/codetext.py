# mashpad/codetext.py — token stream for BabyIDE mode.
#
# Pure — no pygame imports (joins the purity test). Streams Mashpad's own source
# code as a sequence of syntax-categorized tokens, one per call, cycling through
# a curated dependency-ordered file list with a persistable resume cursor.

from __future__ import annotations

import io
import json
import keyword
import os
import tokenize as _tok
from dataclasses import dataclass
from pathlib import Path

from mashpad import config


# ---------------------------------------------------------------------------
# Token model + tokenizer
# ---------------------------------------------------------------------------

@dataclass
class Token:
    text: str      # source text of the token
    category: str  # keyword | string | comment | number | name | op
    row: int       # 1-based source line
    col: int       # 0-based start column


_STRUCTURAL = {
    _tok.NEWLINE, _tok.NL, _tok.INDENT, _tok.DEDENT,
    _tok.ENCODING, _tok.ENDMARKER,
}

_STRING_TYPES = {_tok.STRING}
for _n in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
    _t = getattr(_tok, _n, None)
    if _t is not None:
        _STRING_TYPES.add(_t)


def _category(tok_type: int, tok_string: str) -> str:
    if tok_type == _tok.COMMENT:
        return "comment"
    if tok_type in _STRING_TYPES:
        return "string"
    if tok_type == _tok.NUMBER:
        return "number"
    if tok_type == _tok.OP:
        return "op"
    if tok_type == _tok.NAME:
        return "keyword" if keyword.iskeyword(tok_string) else "name"
    return "name"  # fallback for any other printable token


def tokenize_source(source: str) -> list[Token]:
    """Tokenize *source* into printable Tokens. Structural tokens (NEWLINE/NL/
    INDENT/DEDENT/ENCODING/ENDMARKER) are dropped — a keypress yields one visible
    word; line breaks/indent are recorded on each token's row/col. A file that
    fails to tokenize returns the tokens collected so far (never raises)."""
    tokens: list[Token] = []
    try:
        for tk in _tok.generate_tokens(io.StringIO(source).readline):
            if tk.type in _STRUCTURAL or not tk.string:
                continue
            tokens.append(
                Token(tk.string, _category(tk.type, tk.string), tk.start[0], tk.start[1])
            )
    except Exception as exc:  # noqa: BLE001 — a weird file must not crash BabyIDE
        print(f"[mashpad babyide] tokenize stopped early: {exc}")
    return tokens


def color_for(category: str):
    """Category -> RGB, defaulting unknown categories to the 'name' color."""
    return config.BABYIDE_TOKEN_COLORS.get(category, config.BABYIDE_TOKEN_COLORS["name"])


# ---------------------------------------------------------------------------
# Curated file list — bottom-up dependency order (leaves → runtime → entry points)
# ---------------------------------------------------------------------------

# Mashpad's own source, in bottom-up dependency order (leaves -> runtime ->
# entry points): what BabyIDE streams. Curated include-list, NOT a glob (a glob
# would drag in test/build/boilerplate files). codetext.py and codepanel.py
# print themselves — the code that prints the code.
SOURCE_FILES = [
    "config.py", "paths.py", "ratelimit.py", "trail.py", "duck.py",
    "keymap.py", "items.py", "imagepack.py", "phrases.py", "melodies.py",
    "voiceselect.py", "combos.py", "settings.py", "splash.py", "audio.py",
    "render.py", "codetext.py", "codelayout.py", "codepanel.py", "menu.py", "lockdown.py",
    "main.py", "__main__.py",
]


# ---------------------------------------------------------------------------
# CodeStream
# ---------------------------------------------------------------------------

class CodeStream:
    """Streams tokens from a curated list of source files, one per call.

    Parameters
    ----------
    filenames:
        Ordered list of source filenames (bare names, not full paths).
    reader:
        ``callable(name) -> str`` — injected so tests don't touch the filesystem.
        If it raises, the file is treated as empty and skipped.
    position:
        Optional ``(filename, token_index)`` resume cursor (from
        ``load_position``). Out-of-range or unknown filename is silently clamped.
    """

    def __init__(self, filenames, reader, position=None):
        self._filenames = list(filenames)
        self._reader = reader
        self._cache: dict[str, list[Token]] = {}
        self._file_idx = 0
        self._tok_idx = 0
        if position is not None:
            self._seek(position)
        self._normalize()
        self._current_file = self._filenames[self._file_idx] if self._filenames else ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tokens_for(self, idx: int) -> list[Token]:
        """Return (cached) token list for file at *idx*."""
        fname = self._filenames[idx]
        if fname not in self._cache:
            try:
                source = self._reader(fname)
            except Exception:  # noqa: BLE001
                print(f"[mashpad babyide] could not read {fname!r}, skipping")
                source = ""
            self._cache[fname] = tokenize_source(source)
        return self._cache[fname]

    def _seek(self, position) -> None:
        """Move the cursor to *position* = ``(filename, token_index)``.

        Unknown filename → reset to ``(0, 0)``.
        Out-of-range token index for a known filename → clamp to 0 (top of file).
        """
        fname, idx = position
        if fname in self._filenames:
            self._file_idx = self._filenames.index(fname)
            tokens = self._tokens_for(self._file_idx)
            self._tok_idx = idx if (0 <= idx < len(tokens)) else 0
        else:
            self._file_idx = 0
            self._tok_idx = 0

    def _normalize(self) -> None:
        """Advance the cursor past any empty files, wrapping at end-of-list.

        Tries at most *n* files (where n = len(filenames)); stops as soon as a
        file with remaining tokens is found. Does NOT modify ``_current_file``.
        """
        n = len(self._filenames)
        if n == 0:
            return
        for _ in range(n):
            tokens = self._tokens_for(self._file_idx)
            if self._tok_idx < len(tokens):
                return  # valid position found
            # Advance to the next file (wrap around)
            self._file_idx = (self._file_idx + 1) % n
            self._tok_idx = 0
        # Fell through — all n files exhausted (all empty). Cursor stays at (0, 0).

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_file(self) -> str:
        """Filename of the token most recently emitted by ``next()``."""
        return self._current_file

    def position(self) -> tuple[str, int]:
        """Return ``(filename, token_index)`` — the normalized cursor (next token
        to emit). Suitable for passing to ``save_position``."""
        if not self._filenames:
            return ("", 0)
        return (self._filenames[self._file_idx], self._tok_idx)

    def next(self) -> Token | None:
        """Emit the next token, advancing the cursor.

        Returns ``None`` only when every file in the list is empty or unreadable.
        Normally wraps around to the first file after the last file is consumed.
        """
        self._normalize()
        if not self._filenames:
            return None
        tokens = self._tokens_for(self._file_idx)
        if self._tok_idx >= len(tokens):
            return None  # all files are empty
        token = tokens[self._tok_idx]
        # Record which file this token came from *before* advancing.
        self._current_file = self._filenames[self._file_idx]
        self._tok_idx += 1
        self._normalize()
        return token


# ---------------------------------------------------------------------------
# Resume persistence (atomic, mirrors settings.save / settings.load)
# ---------------------------------------------------------------------------

def save_position(position, path) -> bool:
    """Write ``(filename, token_index)`` to *path* atomically.

    Uses the same tmp → flush → os.fsync → os.replace idiom as settings.save.
    Returns True on success, False on OSError (e.g. SD card read-only or full).
    """
    fname, idx = position
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    data = {"file": fname, "token_index": int(idx)}
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)  # atomic on the same filesystem
    except OSError as exc:
        print(f"[mashpad babyide] could not save position {path}: {exc}")
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


def load_position(path):
    """Return ``(filename, token_index)`` from *path*, or ``None`` on any problem.

    Missing file, bad JSON, non-dict, or invalid field values all return None
    (the caller falls back to starting from the top). Mirrors settings.load.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    fname = raw.get("file")
    idx = raw.get("token_index")
    # Require non-empty string filename and non-negative, non-bool int index.
    if not isinstance(fname, str) or not fname:
        return None
    if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
        return None
    return (fname, idx)
