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

# Maximum number of live (non-dead) items on screen at once.
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
MIXER_CHANNELS = 8

# Rendered size (diameter / side) of each item in pixels at scale=1.0.
ITEM_SIZE_PX = 280
