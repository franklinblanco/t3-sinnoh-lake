"""Start the installed monitor with the T3 data directory selected at install time."""
import json
import os
from pathlib import Path
import sys

if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    os.environ.setdefault("T3CODE_HOME", json.loads((directory / "t3-home.json").read_text("utf-8")))
    sys.argv.extend(["--log", str(directory / "monitor.log")])
    from sinnoh.monitor import main

    sys.exit(main())
