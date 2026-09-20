from pathlib import Path

from sim_world import WorldService

from .runway import RunwayFootprint
from .world_elevation import simulator_elevation


def simulator_world(root):
    root = Path(root)
    exclude = RunwayFootprint(root) if (root / 'config/airfield.json').exists() else None
    return WorldService(root, simulator_elevation(root), exclude)
