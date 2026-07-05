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
        # Voice/phrase clips are LAZY: the maps hold Paths, decoded to Sounds on
        # first play and cached. Eager-decoding a full multi-voice pack set
        # (1000+ OGGs) costs seconds of startup and ~150MB on a 1GB Pi.
        # voice name → { word → [Path take, ...] }
        self._voice: dict[str, dict[str, list[Path]]] = {}
        # voice name → { trigger → [Path, ...] } (phrase-*.ogg clips)
        self._phrases: dict[str, dict[str, list[Path]]] = {}
        self._cache: dict[Path, "pygame.mixer.Sound | None"] = {}
        self._effects: list["pygame.mixer.Sound"] = []  # 8 small clips — eager
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
                clip = self._sound(rng.choice(takes))
                if clip is not None:
                    clip.set_volume(self._master)
                    self._play(clip)
        if self._effects:
            effect = rng.choice(self._effects)
            effect.set_volume(0.7 * self._master)
            self._play(effect)

    def play_phrase(self, trigger: str, rng, voice=None) -> None:
        """Play a random 'phrase-<trigger>-*' clip in *voice*.

        Prefers *voice*'s own phrase pack; if that voice has no clip for the
        trigger (or voice is None), falls back to the first other pack that
        does. Silent when no pack has the clip or the mixer is unavailable.
        """
        if not self._ok:
            return
        clips = None
        if voice is not None:
            pack = self._phrases.get(voice)
            if pack:
                clips = pack.get(trigger)
        if not clips:
            for pack in self._phrases.values():
                found = pack.get(trigger)
                if found:
                    clips = found
                    break
        if not clips:
            return
        clip = self._sound(rng.choice(clips))
        if clip is None:
            return
        clip.set_volume(self._master)
        self._play(clip)

    # ----------------------------------------------------------------- loading

    def _load(self) -> None:
        root = repo_root()
        self._voice, self._phrases = self._load_voices(root / "sounds" / "voice")
        self._effects = self._load_effects(root / "sounds" / "effects")

    def _load_voices(self, directory: Path):
        """Discover voice packs under *directory*.

        Returns ({voice: {word: [Sound]}}, {voice: {trigger: [Sound]}}) — spoken
        words and reactive-phrase clips kept in separate maps so phrase clips are
        never picked as a spoken word.
        """
        voices: dict[str, dict[str, list]] = {}
        phrases: dict[str, dict[str, list]] = {}
        if not directory.is_dir():
            return voices, phrases
        # Sub-directory packs: sounds/voice/<name>/<word>-<take>.ogg|.wav
        for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
            words, pack_phrases = self._load_pack(sub)
            if words:
                voices[sub.name] = words
            if pack_phrases:
                phrases[sub.name] = pack_phrases
        # Legacy flat files directly under sounds/voice/ → the "default" voice.
        flat_words, flat_phrases = self._load_pack(directory)
        if flat_words and "default" not in voices:
            voices["default"] = flat_words
        if flat_phrases and "default" not in phrases:
            phrases["default"] = flat_phrases
        return voices, phrases

    def _load_pack(self, directory: Path):
        """Scan one voice directory into ({word: [Path]}, {trigger: [Path]}).

        Files whose stem starts with 'phrase-' are reactive-phrase clips keyed by
        trigger and excluded from the word map; everything else is a spoken word.
        Paths only — decoding happens lazily in _sound() at play time.
        """
        words: dict[str, list] = {}
        phrases: dict[str, list] = {}
        files = sorted(directory.glob("*.ogg")) + sorted(directory.glob("*.wav"))
        for path in files:
            stem = path.stem
            if stem.startswith("phrase-"):
                trigger = self._phrase_trigger(stem)
                if trigger:
                    phrases.setdefault(trigger, []).append(path)
                continue
            word, _take = self._split_word_take(stem)
            words.setdefault(word, []).append(path)
        return words, phrases

    def _sound(self, path: Path):
        """Decode *path* to a Sound, cached. A bad file warns once, then None."""
        if path in self._cache:
            return self._cache[path]
        try:
            sound = pygame.mixer.Sound(str(path))
        except Exception as exc:  # noqa: BLE001 — skip the bad file only
            print(f"[mashpad audio] could not load {path.name}: {exc}")
            sound = None
        self._cache[path] = sound
        return sound

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

    @staticmethod
    def _phrase_trigger(stem: str):
        """'phrase-slowdown-3' → 'slowdown'; 'phrase-fun' → 'fun'; 'phrase-' → None."""
        rest = stem[len("phrase-"):]
        if not rest:
            return None
        trigger, _take = Audio._split_word_take(rest)
        return trigger

    # ---------------------------------------------------------------- playback

    def _play(self, sound: "pygame.mixer.Sound") -> None:
        # find_channel() returns None when every channel is busy — skip rather
        # than block or forcibly steal a playing channel.
        channel = pygame.mixer.find_channel()
        if channel is None:
            return
        channel.play(sound)
