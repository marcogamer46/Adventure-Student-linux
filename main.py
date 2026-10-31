"""Open the Adventure workbench without arguments from an IDE or terminal."""
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    from adventure_setup import SetupError, launch
    if len(sys.argv) != 1:
        print("Open main.py without arguments. Use workbench.py for the optional command interface.", file=sys.stderr)
        return 2
    try:
        return launch(root)
    except SetupError as exc:
        print(exc.message, file=sys.stderr)
        return 2
    except (OSError, ImportError):
        print("Adventure could not open its workbench files. Run SETUP.cmd, or extract a fresh copy of the supplied project.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
