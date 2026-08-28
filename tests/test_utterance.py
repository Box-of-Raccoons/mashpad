# Tests for Audio.speak() — the multi-clip utterance queue behind the challenge
# announcer ("Find the letter" … "B") — plus Audio.challenge_voice(), which
# picks the pack that owns the carrier clips.
#
# Covered: both clips scheduled UTTERANCE_GAP_S apart under ONE duck window; the
# second clip is not launched early; an unresolvable stem speaks nothing at all;
# cancel clears the queue and releases the duck; a second speak cancels the
# first; the `speaking` flag tracks pending-then-sounding.
#
# Runs each scenario in a subprocess (like test_audio_effect_fallback.py) so
# mashpad.audio / pygame are never imported into the pytest process and cannot
# break the purity assertion in test_keymap.py.

import subprocess
import sys


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


# Shared preamble: an Audio wired to fakes, so no mixer is ever initialised.
_PRE = r"""
import sys
import pygame
from mashpad import config
from mashpad.audio import Audio
from mashpad.duck import DuckWindow

# update() walks the bed channels through the real mixer; reporting only the
# phrase channel leaves that loop empty, so no mixer init is needed.
pygame.mixer.get_num_channels = lambda: config.PHRASE_CHANNEL + 1

LEAD = config.PHRASE_LEAD_S
GAP = config.UTTERANCE_GAP_S
F = config.PHRASE_DUCK_FACTOR
UP = config.PHRASE_DUCK_FADE_UP_S


class FakeSound:
    def __init__(self, tag, length=1.0):
        self.tag = tag
        self.length = length
        self.vol = None
    def get_length(self):
        return self.length
    def set_volume(self, v):
        self.vol = v


class FakeChannel:
    def __init__(self):
        self.played = []
        self.stops = 0
        self.busy = False
        self.vol = None
    def set_volume(self, v):
        self.vol = v
    def play(self, sound):
        self.played.append(sound)
        self.busy = True
    def stop(self):
        self.stops += 1
        self.busy = False
    def get_busy(self):
        return self.busy


class FakeRng:
    def choice(self, seq):
        return seq[0]


def make(packs):
    # packs: {voice: {stem: FakeSound}}. Each Sound is pre-seeded into the decode
    # cache under a string key, so _sound() returns it without touching pygame.
    a = Audio.__new__(Audio)
    a._ok = True
    a._master = 1.0
    a._duck = DuckWindow()
    a._pending_phrase = None
    a._utterance = []
    a._utterance_active = False
    a._phrase_channel = FakeChannel()
    a._cache = {}
    a._voice = {}
    for voice, stems in packs.items():
        a._voice[voice] = {}
        for stem, sound in stems.items():
            key = voice + "/" + stem
            a._cache[key] = sound
            a._voice[voice][stem] = [key]
    return a


def ask_pack():
    return {"v": {"find-the-letter": FakeSound("carrier", 1.0),
                  "b": FakeSound("b", 0.5)}}


def fail(msg):
    print("FAIL: " + msg)
    sys.exit(1)


def close(a, b):
    return abs(a - b) < 1e-9
"""


def test_two_stem_utterance_schedules_both_with_gap():
    proc = _run(_PRE + r"""
a = make(ask_pack())
ok = a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0)
if ok is not True:
    fail("speak returned %r" % (ok,))
if len(a._utterance) != 2:
    fail("queue %r" % (a._utterance,))
tags = [c.tag for c, _ in a._utterance]
if tags != ["carrier", "b"]:
    fail("order %r" % (tags,))
starts = [s for _, s in a._utterance]
want = [100.0 + LEAD, 100.0 + LEAD + 1.0 + GAP]
if not (close(starts[0], want[0]) and close(starts[1], want[1])):
    fail("starts %r want %r" % (starts, want))
if [c.vol for c, _ in a._utterance] != [1.0, 1.0]:
    fail("clip volumes not set to master")
# ONE duck window over the whole thing: still ducked in the gap and at the end
if a._duck.factor(want[0] + 1.0 + GAP / 2) != F:
    fail("bed came back up during the gap")
if a._duck.factor(want[1] + 0.5 - 0.01) != F:
    fail("bed came back up before the last clip ended")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_second_clip_not_launched_early():
    proc = _run(_PRE + r"""
a = make(ask_pack())
a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0)
first = 100.0 + LEAD
second = first + 1.0 + GAP
a.update(first - 0.01)
if a._phrase_channel.played:
    fail("first clip launched before its start time")
a.update(first)
if [s.tag for s in a._phrase_channel.played] != ["carrier"]:
    fail("after first start: %r" % ([s.tag for s in a._phrase_channel.played],))
a.update(second - 0.01)
if [s.tag for s in a._phrase_channel.played] != ["carrier"]:
    fail("second clip launched early: %r" % ([s.tag for s in a._phrase_channel.played],))
a.update(second)
if [s.tag for s in a._phrase_channel.played] != ["carrier", "b"]:
    fail("after second start: %r" % ([s.tag for s in a._phrase_channel.played],))
if a._utterance:
    fail("queue not drained: %r" % (a._utterance,))
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_missing_stem_speaks_nothing():
    proc = _run(_PRE + r"""
a = make(ask_pack())
if a.speak(("find-the-letter", "zz"), "v", FakeRng(), now=100.0) is not False:
    fail("missing stem should return False")
if a._utterance:
    fail("a missing stem still scheduled %r" % (a._utterance,))
if a._duck.factor(100.0 + LEAD) != 1.0:
    fail("a missing stem still ducked the bed")
if a.speak(("find-the-letter",), "nosuchvoice", FakeRng(), now=100.0) is not False:
    fail("unknown voice should return False")
if a.speak(("find-the-letter",), None, FakeRng(), now=100.0) is not False:
    fail("voice=None should return False")
if a._utterance:
    fail("queue should still be empty")
# an in-flight utterance survives a later speak() that cannot resolve
a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0)
before = list(a._utterance)
a.speak(("zz",), "v", FakeRng(), now=101.0)
if a._utterance != before:
    fail("failed speak() disturbed the in-flight utterance")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_cancel_clears_queue_and_releases_duck():
    proc = _run(_PRE + r"""
a = make({"v": {"find-the-letter": FakeSound("carrier", 1.0),
                "b": FakeSound("b", 30.0)}})     # a long ask, like counting
a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0)
first = 100.0 + LEAD
a.update(first)
t = first + 0.5
if a._duck.factor(t) != F:
    fail("expected a ducked bed mid-utterance")
a.cancel_speech(t)
if a._utterance:
    fail("cancel left %r queued" % (a._utterance,))
if a._phrase_channel.stops < 1:
    fail("cancel did not stop the phrase channel")
if a.speaking:
    fail("still speaking after cancel")
if a._duck.factor(t) != F:
    fail("cancel popped the bed straight to full volume")
if not close(a._duck.factor(t + UP / 2), (1.0 + F) / 2):
    fail("fade-up did not start at the cancel: %r" % (a._duck.factor(t + UP / 2),))
if a._duck.factor(t + UP + 0.01) != 1.0:
    fail("bed never returned to full volume")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_second_speak_cancels_the_first():
    proc = _run(_PRE + r"""
a = make({"v": {"find-the-letter": FakeSound("carrier", 1.0),
                "b": FakeSound("b", 0.5),
                "c": FakeSound("c", 0.5)}})
a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0)
a.update(100.0 + LEAD)
if a.speak(("c",), "v", FakeRng(), now=101.0) is not True:
    fail("second speak should schedule")
tags = [c.tag for c, _ in a._utterance]
if tags != ["c"]:
    fail("first utterance was not cancelled: %r" % (tags,))
if not close(a._utterance[0][1], 101.0 + LEAD):
    fail("second utterance start %r" % (a._utterance[0][1],))
if a._phrase_channel.stops < 1:
    fail("second speak did not stop the sounding clip")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_speaking_flag_tracks_pending_then_sounding():
    proc = _run(_PRE + r"""
a = make(ask_pack())
if a.speaking:
    fail("a fresh Audio should not be speaking")
a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0)
if not a.speaking:
    fail("not speaking while the queue is pending")
a.update(100.0 + LEAD)
if not a.speaking:
    fail("not speaking with a clip on the channel and one still queued")
a.update(100.0 + LEAD + 1.0 + GAP)
if a._utterance:
    fail("queue should be drained")
if not a.speaking:
    fail("not speaking while the last clip is still sounding")
a._phrase_channel.busy = False                  # the clip finished
if a.speaking:
    fail("still speaking after the queue drained and the clip ended")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_silent_mode_speak_is_a_noop():
    proc = _run(_PRE + r"""
a = make(ask_pack())
a._ok = False
if a.speak(("find-the-letter", "b"), "v", FakeRng(), now=100.0) is not False:
    fail("silent mode should return False")
if a._utterance:
    fail("silent mode scheduled %r" % (a._utterance,))
a.cancel_speech(100.0)                          # must not raise
if a.speaking:
    fail("silent mode should never report speaking")
if a.challenge_voice(("find-the-letter", "b")) is not None:
    fail("silent mode should have no challenge voice")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


# ---------------------------------------------------------------------------
# challenge_voice
# ---------------------------------------------------------------------------

_PACKS = r"""
def carriers():
    return {"find-the-letter": FakeSound("carrier"), "b": FakeSound("b")}

a = make({"alpha": carriers(), "zeta": carriers(),
          "nope": {"b": FakeSound("b")}})
NEED = ("find-the-letter", "b")
"""


def test_challenge_voice_prefers_the_selected_pack():
    proc = _run(_PRE + _PACKS + r"""
got = a.challenge_voice(NEED, preferred="zeta")
if got != "zeta":
    fail("preferred qualifying pack lost: %r" % (got,))
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_challenge_voice_falls_through_when_preferred_lacks_carriers():
    proc = _run(_PRE + _PACKS + r"""
got = a.challenge_voice(NEED, preferred="nope")
if got != "alpha":
    fail("expected the first qualifying pack in sorted order, got %r" % (got,))
got = a.challenge_voice(NEED)                   # no preference at all
if got != "alpha":
    fail("expected alpha with no preference, got %r" % (got,))
got = a.challenge_voice(NEED, preferred="not-a-pack")
if got != "alpha":
    fail("a preferred name that isn't a pack should fall through, got %r" % (got,))
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"


def test_challenge_voice_none_when_nothing_qualifies():
    proc = _run(_PRE + _PACKS + r"""
got = a.challenge_voice(("find-the-number", "7"), preferred="zeta")
if got is not None:
    fail("expected None when no pack has the carriers, got %r" % (got,))
b = make({})                                    # no packs loaded at all
if b.challenge_voice(NEED) is not None:
    fail("expected None with no packs")
sys.exit(0)
""")
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
