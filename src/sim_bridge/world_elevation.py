import json
from dataclasses import asdict, replace
from pathlib import Path

from sim_launcher.config import load_simulation_config
from sim_world.elevation import WorldElevation, build_elevation_source, terrain_cache

from .runway import RunwaySurface


class SimulatorElevation(WorldElevation):
    def __init__(self, root):
        root = Path(root)
        config = load_simulation_config(root / 'config/simulation.yaml')
        self.settings = json.loads((root / 'config/terrain-preparation.json').read_text())
        self.airfield = json.loads((root / 'config/airfield.json').read_text(encoding='utf-8-sig'))
        self.home = config.polygon
        cache = terrain_cache(root) if (root / 'config/terrain-streaming.json').exists() else None
        super().__init__(
            build_elevation_source(replace(config.terrain, geoid_separation_m=0.0)),
            self.settings['grid_size'],
            config.terrain.geoid_separation_m,
            cache,
            RunwaySurface(asdict(config.polygon), self.airfield, self.settings['airfield_blend_m']),
        )


def simulator_elevation(root):
    root = Path(root)
    if not (root / 'config/simulation.yaml').exists() or not (root / 'config/terrain-preparation.json').exists():
        return None
    return SimulatorElevation(root)
