from pathlib import Path
import os

ASSETS = Path(__file__).resolve().parent.parent / "assets"
THEME_ID = "sinnoh-lake-life"


def t3_home():
    return Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3").expanduser()
