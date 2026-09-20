"""Installed JSBSim aircraft and the active local airframe."""
import json
import shutil
from pathlib import Path


class AircraftCatalog:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'config/local.aircraft.json'
        self.data = json.loads((self.root / 'config/aircraft-catalog.json').read_text(encoding='utf-8'))
        for path in sorted((self.root/'config/custom-aircraft').glob('*.json')):
            self.data['aircraft'].append(json.loads(path.read_text(encoding='utf-8')))

    def selected(self):
        selected = json.loads(self.path.read_text())['id'] if self.path.exists() else self.data['default']
        return self.get(selected)

    def get(self, aircraft_id):
        for aircraft in self.data['aircraft']:
            if aircraft['id'] == aircraft_id:
                return aircraft
        raise ValueError('Неизвестный самолёт')

    def activate(self, aircraft_id):
        self.prepare(self.get(aircraft_id))
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'id': aircraft_id}), encoding='utf-8')
        temporary.replace(self.path)

    def prepare(self, aircraft=None):
        aircraft = aircraft or self.selected()
        if aircraft['source'] == 'ardupilot':
            return
        import importlib.util
        spec = importlib.util.spec_from_file_location('prepare_aircraft_assets', self.root / 'scripts/prepare_jsbsim_root.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        from sim_launcher.config import load_simulation_config
        config = load_simulation_config(self.root / 'config/simulation.yaml')
        source = self.root / 'third_party/jsbsim'
        target = self.root / 'build/jsbsim_root/instance-0'
        model = aircraft['model']
        model_dir = target / 'aircraft' / model
        shutil.copytree(source / 'aircraft' / model, model_dir, dirs_exist_ok=True)
        for directory in ('engine', 'systems'):
            if (source / directory).exists():
                shutil.copytree(source / directory, target / directory, dirs_exist_ok=True)
        model_file = model_dir / f'{model}.xml'
        import xml.etree.ElementTree as ET
        tree=ET.parse(model_file)
        fcs=tree.find('flight_control')
        if aircraft.get('external_flight_control'):
            from sim_bridge.f16_control_adapter import apply_external_controls
            apply_external_controls(tree)
        for name,value in aircraft.get('initial_properties', {}).items():
            existing=fcs.find(f"property[.='{name}']")
            if existing is not None:existing.text=name;existing.set('value',str(value))
            else:ET.SubElement(fcs,'property',value=str(value)).text=name
        if aircraft.get('idle_parking_brake', False):
            # The turbine makes idle thrust. Hold wheel brakes until throttle is commanded.
            channel=ET.SubElement(fcs,'channel',name='Simulator idle parking brake')
            for side in ('left','right','center'):
                switch=ET.SubElement(channel,'switch',name=f'flightlab/{side}-parking-brake')
                ET.SubElement(switch,'default',value='0')
                ET.SubElement(switch,'test',value='1').text='fcs/throttle-cmd-norm le 0.001'
                ET.SubElement(switch,'output').text=f'fcs/{side}-brake-cmd-norm'
        tree.write(model_file,encoding='utf-8',xml_declaration=True)
        helper._inject_terrain_input_socket(model_file, config.jsbsim.terrain_input_port(0))
        helper._inject_pose_output_socket(target, model_file, config.jsbsim.pose_output_port(0), config.jsbsim.pose_output_hz, config.jsbsim.pose_output_host)
