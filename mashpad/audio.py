# mashpad/audio.py — sound-clip loading + playback.
#
# Degrades silently in every failure mode: --mute, mixer init failure, missing
# sound directories, empty directories, or an unloadable WAV. In silent mode all
# play calls are no-ops. pygame is imported at module load (cheap, no display),
# but the mixer is only touched inside Audio.__init__.

from __future__ import annotations

from pathlib import Path

import pygame

from mashpad import config


def repo_root() -> Path:
    """Repo root = parent of the `mashpad` package dir (not CWD)."""
    return Path(__file__).resolve().parent.parent


class Audio:
    """Loads voice + effect WAVs and plays them without ever blocking or stealing."""

    def __init__(self, muted: bool = False) -> None:
        self._ok: bool = False
        self._voice: dict[str, "pygame.mixer.Sound"] = {}
        self._effects: list["pygame.mixer.Sound"] = []

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

    def _load(self) -> None:
        root = repo_root()
        self._voice = self._load_dir(root / "sounds" / "voice", as_map=True)
        self._effects = self._load_dir(root / "sounds" / "effects", as_map=False)

    def _load_dir(self, directory: Path, as_map: bool):
        result_map: dict[str, "pygame.mixer.Sound"] = {}
        result_list: list["pygame.mixer.Sound"] = []
        if directory.is_dir():
            for wav in sorted(directory.glob("*.wav")):
                try:
                    sound = pygame.mixer.Sound(str(wav))
                except Exception as exc:  # noqa: BLE001 — skip the bad file only
                    print(f"[mashpad audio] could not load {wav.name}: {exc}")
                    continue
                if as_map:
                    result_map[wav.stem] = sound
                else:
                    result_list.append(sound)
        return result_map if as_map else result_list

    def play_for(self, spec, rng) -> None:
        """Play the voice clip for spec.name (if loaded) plus a random effect (if any)."""
        if not self._ok:
            return
        clip = self._voice.get(spec.name)
        if clip is not None:
            self._play(clip)
        if self._effects:
            self._play(rng.choice(self._effects))

    def _play(self, sound: "pygame.mixer.Sound") -> None:
        # find_channel() returns None when every channel is busy — skip rather
        # than block or forcibly steal a playing channel.
        channel = pygame.mixer.find_channel()
        if channel is None:
            return
        channel.play(sound)
