# PyInstaller entry point for the desktop edition.
# Equivalent to `python -m mashpad` — kept as a real file because PyInstaller
# wants a script, not a -m module path.

from mashpad.main import main

if __name__ == "__main__":
    main()
