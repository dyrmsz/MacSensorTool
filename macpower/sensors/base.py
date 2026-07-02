"""
The sensor contract.

A sensor is any module in macpower.sensors that exposes:

    NAME: str                     unique id, used on the CLI and in URLs
    DESCRIPTION: str              one line for --list and the HTTP index
    available() -> bool           can this sensor run on this machine?
    read() -> dict                fetch raw data (subprocess, files, ...)
    derive(raw: dict) -> dict     pure: raw -> friendly values (JSON-safe)
    render(derived: dict) -> str  pure: friendly values -> terminal text

Optional:
    summary(derived: dict) -> str one short line for menu bar displays

Keep read() as the only impure function so derive() and render() can be
unit-tested with mock dicts on any OS. Register new sensors in
macpower/sensors/__init__.py.
"""

import subprocess
import sys


def sh(*argv: str) -> str:
    """Run a command, return stdout as text ('' on failure)."""
    try:
        return subprocess.run(
            list(argv), capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def ansi(txt, code):
    """Wrap txt in an ANSI color when writing to a real terminal."""
    if sys.stdout.isatty():
        return f"\x1b[{code}m{txt}\x1b[0m"
    return str(txt)
