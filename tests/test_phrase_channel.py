# Regression: a phrase must be audible even when mashing has every mixer
# channel busy (the exact moment slowdown/screenfull triggers fire).
#
# Needs a real mixer, and the purity tests forbid pygame inside the pytest
# process — so the scenario runs in a subprocess and reports via exit code.

import subprocess
import sys

SCENARIO = r"""
import random, sys, time, pygame
from mashpad import config
from mashpad.audio import Audio

class Spec:
    spoken_name = "a"

pygame.init()
audio = Audio(muted=False)
if not audio.voices:
    sys.exit(0)  # no packs on this checkout - nothing to assert
rng = random.Random(7)
for _ in range(6):                     # saturate the bed channels
    audio.play_for(Spec(), rng, audio.voices[0])
time.sleep(0.05)
if pygame.mixer.Channel(0).get_busy():
    sys.exit(2)  # bed leaked onto the phrase channel
audio.play_phrase("slowdown", rng, audio.voices[0])
# pump update() like the main loop until the scheduled start has passed,
# mashing all the while so the bed stays busy
deadline = time.time() + config.PHRASE_LEAD_S + 0.3
k = 0
while time.time() < deadline:
    audio.update(pygame.time.get_ticks() / 1000.0)
    k += 1
    if k % 15 == 0:
        audio.play_for(Spec(), rng, audio.voices[0])
    time.sleep(0.01)
phrase_ok = (pygame.mixer.Channel(0).get_busy()
             and pygame.mixer.Channel(0).get_volume() > 0.99)
bed = [round(pygame.mixer.Channel(i).get_volume(), 2)
       for i in range(1, pygame.mixer.get_num_channels())
       if pygame.mixer.Channel(i).get_busy()]
bed_ducked = all(v < 1.0 for v in bed) and len(bed) >= 1
# the phrase is speaking at full volume on the reserved channel over a ducked bed
sys.exit(0 if (phrase_ok and bed_ducked) else 1)
"""


def test_phrase_survives_channel_saturation():
    proc = subprocess.run([sys.executable, "-c", SCENARIO], capture_output=True, text=True)
    assert proc.returncode != 2, "bed audio leaked onto the phrase channel (0)"
    assert proc.returncode == 0, (
        f"phrase was dropped or not ducked under saturation\n{proc.stdout}\n{proc.stderr}"
    )
