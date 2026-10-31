"""Prepare Adventure's local environment. Normally start with SETUP.cmd."""
from pathlib import Path
import argparse
import json
import sys


def main(argv=None):
    root = Path(__file__).absolute().parent
    sys.path.insert(0, str(root))
    from adventure_setup import SetupError, prepare_environment
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--prepare-only", action="store_true", help="Prepare files without claiming the graphical check passed")
    parser.add_argument("--bundled-offline", action="store_true", help="Use only the complete supplied runtime and wheel")
    args = parser.parse_args(argv)
    try:
        result = prepare_environment(root, offline=args.offline, artifact_dir=args.artifact_dir,
            prepare_only=args.prepare_only, bundled=args.bundled_offline, progress=lambda text: print(text, flush=True))
        if result["ready"]:
            print("Setup complete. Open START.cmd, or open main.py in your IDE.")
        else:
            print("Environment files are prepared. The graphical check is still pending; run SETUP.cmd before using Adventure.")
        print(json.dumps({key: result[key] for key in ("status", "ready", "student_code_executed")}))
        return 0
    except SetupError as exc:
        print(exc.message, file=sys.stderr)
        print("Setup status: " + exc.code, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Setup interrupted. Close this window and retry SETUP.cmd; your student files and saved runs stay in place.", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("Setup could not write or check this project. Extract it to a writable folder and retry; keep your student files and saved runs.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
