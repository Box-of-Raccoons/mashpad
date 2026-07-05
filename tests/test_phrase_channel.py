# Regression: a phrase must be audible even when mashing has every mixer
# channel busy (the exact moment slowdown/screenfull triggers fire).
#
# Needs a real mixer, and the purity tests forbid pygame inside the pytest
# process — so the scenario runs in a subprocess and reports via exit code.

import subprocess
import sys

SCENARIO = r"""
import random, sys, time, pygame
from mashpad.audio import Audio

class Spec:
    spoken_name = "a"

pygame.init()
audio = Audio(muted=False)
if not audio.voices:
    sys.exit(0)  # no packs on this checkout - nothing to assert
rng = random.Random(7)
for _ in range(6):                     # saturate the non-reserved channels
    audio.play_for(Spec(), rng, audio.voices[0])
time.sleep(0.05)
audio.play_phrase("slowdown", rng, audio.voices[0])
time.sleep(0.05)
vols = [round(pygame.mixer.Channel(i).get_volume(), 2)
        for i in range(pygame.mixer.get_num_channels())
        if pygame.mixer.Channel(i).get_busy()]
full = vols.count(1.0)
ducked = sum(1 for v in vols if v < 1.0)
# exactly one full-volume channel (the phrase) and a ducked bed
sys.exit(0 if (full == 1 and ducked >= 1) else 1)
"""


def test_phrase_survives_channel_saturation():
    proc = subprocess.run([sys.executable, "-c", SCENARIO], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"phrase was dropped or not ducked under saturation\n{proc.stdout}\n{proc.stderr}"
    )
