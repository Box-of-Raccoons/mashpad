import os

# Must be set before pygame is first imported anywhere: hides the
# "pygame x.y.z / Hello from the pygame community" banner, which is noise on
# tty1 and gets spoken aloud if a console screen reader is active.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

__version__ = "1.0.0-SNAPSHOT"
