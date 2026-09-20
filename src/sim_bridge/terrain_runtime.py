"""Start terrain feeders only for simulator instances that publish a pose."""
import atexit
from .world_elevation import SimulatorElevation
from sim_launcher.jsbsim_terrain_feeder import JsbSimTerrainFeeder

class TerrainRuntime:
    def __init__(self, root, config):
        self.root=root
        self.generation=None
        self.elevation=SimulatorElevation(root)
        self.config=config
        self.positions={}
        self.feeders={}
        atexit.register(self.close)

    def observe(self,pose):
        generation=pose.get('generation',0)
        if generation!=self.generation:
            from sim_launcher.config import load_simulation_config
            self.close()
            self.config=load_simulation_config(self.root/'config/simulation.yaml')
            self.elevation=SimulatorElevation(self.root)
            self.generation=generation
        if not self.elevation.available:return
        if self.elevation.cache:self.elevation.cache.observe(pose)
        index=int(pose['instance_index'])
        self.positions[index]=(pose['latitude_deg'],pose['longitude_deg'])
        if index in self.feeders:return
        c=self.config
        feeder=JsbSimTerrainFeeder(c.jsbsim.bind_host,c.jsbsim.terrain_input_port(index),self.elevation,
            lambda:self.positions[index],1/c.terrain.update_hz,index,c.terrain.max_change_rate_m_per_s,c.polygon.home_elevation_asl_m)
        self.feeders[index]=feeder
        feeder.start()

    def close(self):
        for feeder in self.feeders.values():feeder.stop()
        self.feeders.clear()
