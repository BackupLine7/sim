"""Apply the training airframe profile only to generated JSBSim assets."""
from pathlib import Path
import xml.etree.ElementTree as ET

class TrainingAirframeAdapter:
    def apply(self, model_file, settings):
        model_file=Path(model_file).resolve()
        # Generated asset only. Never accept a source/submodule path.
        if 'build' not in model_file.parts or 'third_party' in model_file.parts:
            raise ValueError('Airframe profiles require a generated build asset')
        tree=ET.parse(model_file)
        wheel=tree.find("./ground_reactions/contact[@name='TAIL_LG']/max_steer")
        if wheel is None:raise ValueError('Training model has no tailwheel')
        wheel.text=str(settings['tailwheel_max_steer_deg'])
        fcs=tree.find('./flight_control')
        channel=fcs.find("channel[@name='Training tailwheel']")
        if channel is not None:fcs.remove(channel)
        channel=ET.SubElement(fcs,'channel',name='Training tailwheel')
        gain=ET.SubElement(channel,'pure_gain',name='training-tailwheel-steering')
        ET.SubElement(gain,'input').text='fcs/rudder-cmd-norm'
        ET.SubElement(gain,'gain').text='1'
        ET.SubElement(gain,'output').text='fcs/steer-cmd-norm'
        tree.write(model_file,encoding='utf-8',xml_declaration=True)
