# mashpad/config.py — ALL tunables; one-line comment per constant.

# 12 fully-saturated HSV-spaced colors (hue step = 360/12 = 30°), RGB tuples.
PALETTE = [
    (255,   0,   0),   # hue   0° red
    (255, 128,   0),   # hue  30° orange
    (255, 255,   0),   # hue  60° yellow
    (128, 255,   0),   # hue  90° chartreuse
    (  0, 255,   0),   # hue 120° green
    (  0, 255, 128),   # hue 150° spring green
    (  0, 255, 255),   # hue 180° cyan
    (  0, 128, 255),   # hue 210° azure
    (  0,   0, 255),   # hue 240° blue
    (128,   0, 255),   # hue 270° violet
    (255,   0, 255),   # hue 300° magenta
    (255,   0, 128),   # hue 330° rose
]

# Names of the eight shapes the app can spawn.
SHAPES = ["circle", "square", "triangle", "star", "heart", "diamond", "pentagon", "ring"]

# Cap on non-fading items: each spawn past this force-fades the oldest, so the
# on-screen total can briefly exceed it by ~BUCKET_REFILL_PER_S × FADE_S while
# they fade out.
MAX_ITEMS = 20

# Target frames per second for the main render loop.
FPS = 60

# Duration of the bounce-in scale animation, in seconds.
BOUNCE_S = 0.3

# How long an item stays fully visible after spawning, in seconds.
LINGER_S = 4.0

# Duration of the fade-out animation, in seconds.
FADE_S = 1.5

# Peak overshoot multiplier during the bounce-in animation.
BOUNCE_OVERSHOOT = 1.15

# Token bucket: burst capacity — spawns beyond this are dropped, not queued.
BUCKET_CAPACITY = 8

# Token bucket: tokens refilled per second (continuous).
BUCKET_REFILL_PER_S = 6.0

# How long a trail point lives before fading out, in seconds.
TRAIL_FADE_S = 0.6

# Maximum number of trail points kept in the deque (oldest evicted when full).
TRAIL_MAX_POINTS = 64

# Number of pygame mixer channels to allocate.
MIXER_CHANNELS = 9  # 8 for letters/effects + 1 reserved for reactive phrases

# Effect-clip volume relative to master (voice clips play at 1.0 × master).
EFFECT_VOLUME = 0.7

# Rendered size (diameter / side) of each item in pixels at scale=1.0.
ITEM_SIZE_PX = 280

# Subdirectory under assets/ that holds custom PNG sticker images.
IMAGES_DIR_NAME = "images"

# Probability a non-letter spawn is an image (when images exist), per setting.
RACCOON_WEIGHTS = {"less": 0.25, "normal": 0.5, "lots": 0.75}

# Filename (under the repo root) where grown-up options persist.
SETTINGS_FILE = "settings.json"

# Known voice packs → (friendly menu label, gender). Unknown packs fall back to
# the name title-cased with gender None (see menu.py / main.py).
VOICE_INFO = {
    "charon": ("Voice 1", "male"),
    "fenrir": ("Voice 2", "male"),
    "algenib": ("Voice 3", "male"),
    "vindemiatrix": ("Voice 4", "female"),
    "achernar": ("Voice 5", "female"),
    "kore": ("Voice 6", "female"),
}

# Copyright year shown in the options-menu About footer.
BUILD_YEAR = 2026

# Company name shown in the options-menu About footer.
COMPANY = "Box of Raccoons LLC"

# Global minimum seconds between ANY two spoken phrases (see phrases.py).
PHRASE_COOLDOWN_S = 30.0

# Probability an eligible (non-hello) phrase trigger actually fires when polled.
PHRASE_CHANCE = 0.5

# Channel volume for non-phrase audio while a phrase clip is speaking.
PHRASE_DUCK_FACTOR = 0.075

# Seconds between a trigger firing and the phrase speaking — the bed ducks
# during this lead so the phrase opening is never lost in the noise.
PHRASE_LEAD_S = 0.45

# Seconds the bed takes to fade down to PHRASE_DUCK_FACTOR when a phrase fires.
PHRASE_DUCK_FADE_DOWN_S = 0.2

# Extra seconds the bed stays ducked after the phrase clip ends.
PHRASE_DUCK_TAIL_S = 0.35

# Seconds the bed takes to fade back to full volume after the tail.
PHRASE_DUCK_FADE_UP_S = 0.5

# Uniform-random window (min, max spawns) between "fun" phrase re-arms.
FUN_EVERY_SPAWNS = (250, 400)

# Live raccoon (image) items on screen that arm the "raccoons" phrase.
RACCOON_PILE_N = 4

# Rate-limiter drops within SLOWDOWN_WINDOW_S that count as mashing → "slowdown".
SLOWDOWN_DROPS = 6

# Sliding window (seconds) over which SLOWDOWN_DROPS drops are counted.
SLOWDOWN_WINDOW_S = 3.0

# Idle seconds with no spawn after which the next spawn re-triggers "hello".
HELLO_IDLE_S = 300.0

# Seconds an armed phrase trigger stays valid before it silently expires.
# Must exceed PHRASE_COOLDOWN_S so a trigger armed during a cooldown still gets
# one shot after the cooldown opens (45 > 30).  Triggers that are continuously
# re-armed (e.g. raccoons pile still on screen) refresh their armed_time each
# re-arm and so never expire.  'hello' is exempt from this TTL.
PHRASE_ARM_TTL_S = 45.0
