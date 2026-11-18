from pathlib import Path
import os
from tempfile import NamedTemporaryFile

ASSETS = Path(__file__).resolve().parent.parent / "assets"
THEME_ID = "sinnoh-lake-life"


def t3_home():
    return Path(os.environ.get("T3CODE_HOME") or Path.home() / ".t3").expanduser()


def atomic_write(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    # Inherit permissions from the destination directory. A private staging
    # directory on Windows can restrict files to the elevated installer token.
    temporary = NamedTemporaryFile(dir=target.parent, prefix=".sinnoh-", suffix=".tmp",
                                   delete=False)
    staged = Path(temporary.name)
    try:
        with temporary:
            temporary.write(data)
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
