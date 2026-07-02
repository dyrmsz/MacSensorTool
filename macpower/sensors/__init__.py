"""
Sensor registry. To add a sensor, create a module implementing the contract
in macpower.sensors.base and add it to the list below.
"""

from macpower.sensors import battery, memory, system

ALL = [battery, memory, system]

REGISTRY = {mod.NAME: mod for mod in ALL}


def get(names=None):
    """Return the requested sensor modules (all available ones by default)."""
    if names:
        missing = [n for n in names if n not in REGISTRY]
        if missing:
            raise KeyError(
                f"unknown sensor(s): {', '.join(missing)}. "
                f"Available: {', '.join(REGISTRY)}"
            )
        return [REGISTRY[n] for n in names]
    return [mod for mod in ALL if mod.available()]
