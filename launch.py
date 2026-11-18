"""Run the installed loopback Pokétch service and solar/context clock."""
import json
import logging
from pathlib import Path

from sinnoh.panel import serve


if __name__ == "__main__":
    directory = Path(__file__).resolve().parent
    logging.basicConfig(filename=directory / "monitor.log", level=logging.INFO,
                        format="%(asctime)s %(message)s")
    config = json.loads((directory / "install.json").read_text(encoding="utf-8"))
    try:
        serve(Path(config["t3_home"]), config["port"])
    except OSError:
        logging.exception("Could not start Pokétch")
        raise SystemExit(1)
