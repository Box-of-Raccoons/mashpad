# mashpad/audio.py — sound-clip loading + playback (voice packs + effects).
#
# Degrades silently in every failure mode: --mute, mixer init failure, missing
# sound directories, empty directories, or an unloadable clip. In silent mode all
# play calls are no-ops. pygame is imported at module load (cheap, no display),
# but the mixer is only touched inside Audio.__init__.
#
# Voice packs (multi-voice):
#   sounds/voice/<voicename>/<word>-<take>.ogg|.wav   → a named voice pack
#       (files grouped by <word>; a file with no "-<digits>" suffix is take 1)
#   sounds/voice/<word>.wav                           → the legacy flat layout,
#       loaded as a single anonymous voice named "default"
# The app works with zero packs, flat files only, or several packs.

from __future__ import annotations

from pathlib import Path

import pygame

from mashpad import config


def repo_root() -> Path:
    """Repo root = parent of the `mashpad` package dir (not CWD)."""
    return Path(__file__).resolve().parent.parent


class Audio:
    """Loads voice packs + effect clips and plays them without blocking or stealing."""

    def __init__(self, muted: bool = False) -> None:
        self._ok: bool = False
        # voice name → { word → [Sound take, ...] }
        self._voice: dict[str, dict[str, list["pygame.mixer.Sound"]]] = {}
        self._effects: list["pygame.mixer.Sound"] = []
        self._master: float = 1.0  # 0.0–1.0, set by set_master_volume()

        if muted:
            print("[mashpad audio] muted (--mute); running silent")
            return

        try:
            pygame.mixer.init()
            pygame.mixer.set_num_channels(config.MIXER_CHANNELS)
        except Exception as exc:  # noqa: BLE001 — any mixer failure → silent mode
            print(f"[mashpad audio] mixer init failed ({exc}); running silent")
            return

        self._ok = True
        self._load()

    # ------------------------------------------------------------------ public

    @property
    def voices(self) -> list[str]:
        """Sorted list of discovered voice-pack names ('default' for flat files)."""
        return sorted(self._voice.keys())

    def set_master_volume(self, master: float) -> None:
        """Set the master volume (0.0–1.0). Applied per-Sound at play time."""
        self._master = max(0.0, min(1.0, float(master)))

    def play_for(self, spec, rng, voice=None) -> None:
        """Play a random take of spec's spoken word in *voice*, plus a random effect.

        voice=None → use the "default" voice if present, else no voice clip (the
        effect still plays). A voice name not among the loaded packs → no voice
        clip. Voice clips play at master volume; effects at 0.7 × master.
        """
        if not self._ok:
            return
        name = voice if voice is not None else "default"
        pack = self._voice.get(name)
        if pack is not None:
            takes = pack.get(spec.spoken_name)
            if takes:
                clip = rng.choice(takes)
                clip.set_volume(self._master)
                self._play(clip)
        if self._effects:
            effect = rng.choice(self._effects)
            effect.set_volume(0.7 * self._master)
            self._play(effect)

    # ----------------------------------------------------------------- loading

    def _load(self) -> None:
        root = repo_root()
        self._voice = self._load_voices(root / "sounds" / "voice")
        self._effects = self._load_effects(root / "sounds" / "effects")

    def _load_voices(self, directory: Path):
        """Discover voice packs under *directory*. Returns {voice: {word: [Sound]}}."""
        voices: dict[str, dict[str, list]] = {}
        if not directory.is_dir():
            return voices
        # Sub-directory packs: sounds/voice/<name>/<word>-<take>.ogg|.wav
        for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
            words = self._load_pack(sub)
            if words:
                voices[sub.name] = words
        # Legacy flat files directly under sounds/voice/ → the "default" voice.
        flat = self._load_pack(directory)
        if flat and "default" not in voices:
            voices["default"] = flat
        return voices

    def _load_pack(self, directory: Path):
        """Load one voice directory: group *.ogg/*.wav by word → {word: [Sound]}."""
        words: dict[str, list] = {}
        files = sorted(directory.glob("*.ogg")) + sorted(directory.glob("*.wav"))
        for path in files:
            word, _take = self._split_word_take(path.stem)
            try:
                sound = pygame.mixer.Sound(str(path))
            except Exception as exc:  # noqa: BLE001 — skip the bad file only
                print(f"[mashpad audio] could not load {path.name}: {exc}")
                continue
            words.setdefault(word, []).append(sound)
        return words

    def _load_effects(self, directory: Path):
        """Load every effect clip under *directory* (flat *.ogg/*.wav)."""
        effects: list = []
        if not directory.is_dir():
            return effects
        for path in sorted(directory.glob("*.ogg")) + sorted(directory.glob("*.wav")):
            try:
                effects.append(pygame.mixer.Sound(str(path)))
            except Exception as exc:  # noqa: BLE001 — skip the bad file only
                print(f"[mashpad audio] could not load {path.name}: {exc}")
        return effects

    @staticmethod
    def _split_word_take(stem: str):
        """'hello-1' → ('hello', 1); 'hello' → ('hello', 1); 'foo-bar-2' → ('foo-bar', 2)."""
        head, _, tail = stem.rpartition("-")
        if head and tail.isdigit():
            return head, int(tail)
        return stem, 1

    # ---------------------------------------------------------------- playback

    def _play(self, sound: "pygame.mixer.Sound") -> None:
        # find_channel() returns None when every channel is busy — skip rather
        # than block or forcibly steal a playing channel.
        channel = pygame.mixer.find_channel()
        if channel is None:
            return
        channel.play(sound)
