#!/usr/bin/env python3
"""Adapt ArduPilot's generated initial attitude to the selected JSBSim model."""
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

for argument in sys.argv[1:]:
    if not argument.startswith('--script='):
        continue
    script_path = Path(argument.split('=', 1)[1]).resolve()
    script = ET.parse(script_path)
    model = script.find('use').get('aircraft')
    if model == 'Rascal':
        continue
    # Rascal's forced ground trim fails for these stock models; let landing gear settle.
    run = script.find('run')
    for event in list(run.findall('event')):
        if any(setting.get('name') == 'simulation/do_simple_trim' for setting in event.findall('set')):
            run.remove(event)
    script.write(script_path, encoding='utf-8', xml_declaration=True)
    model_dir = Path.cwd() / 'aircraft' / model
    source = ET.parse(model_dir / 'reset00.xml')
    reset_path = model_dir / 'reset.xml'
    reset = ET.parse(reset_path)
    for name in ('altitude', 'theta', 'phi'):
        original = source.find(name)
        target = reset.find(name)
        if original is not None and target is not None:
            target.attrib.clear()
            target.attrib.update(original.attrib)
            target.text = original.text
    reset.write(reset_path, encoding='utf-8', xml_declaration=True)

executable = os.environ['FLIGHTLAB_JSBSIM_BINARY']
os.execv(executable, [executable, *sys.argv[1:]])
