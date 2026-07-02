"""
LaunchAgent management for the background history collector.

--install-agent writes ~/Library/LaunchAgents/com.macpower.collector.plist
and loads it with launchctl so `--collect` keeps sampling sensors into
history.py's SQLite log even when no terminal is open. --uninstall-agent
reverses it. Neither runs unless the user invokes the corresponding CLI
flag themselves -- this module never calls launchctl on its own.
"""

import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.macpower.collector"
PLIST_PATH = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
LOG_DIR = Path.home() / "Library/Logs/macpower"


def install(interval: float = 10.0) -> None:
    script = Path(__file__).resolve().parent.parent / "macpower.py"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    plist = {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, str(script), "--collect", "--interval", str(interval)],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(LOG_DIR / "collector.log"),
        "StandardErrorPath": str(LOG_DIR / "collector.err.log"),
    }
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)
    print(f"Installed and loaded {LABEL}\n  plist: {PLIST_PATH}\n  logs:  {LOG_DIR}")


def uninstall() -> None:
    if not PLIST_PATH.exists():
        print(f"{LABEL} is not installed")
        return
    subprocess.run(["launchctl", "unload", "-w", str(PLIST_PATH)])
    PLIST_PATH.unlink()
    print(f"Unloaded and removed {LABEL}")
