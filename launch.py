"""Start the installed monitor with the T3 data directory selected at install time."""
import json
import logging
import os
from pathlib import Path
import sys


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    log = directory / "monitor.log"
    try:
        os.environ.setdefault("T3CODE_HOME", json.loads((directory / "t3-home.json").read_text("utf-8")))
        sys.argv.extend(["--log", str(log)])
        from sinnoh.monitor import main

        sys.exit(main())
    except Exception:
        logging.basicConfig(filename=log)
        logging.exception("Pokétch could not start")
        sys.exit(1)
