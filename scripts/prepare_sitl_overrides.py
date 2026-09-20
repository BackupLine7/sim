"""Apply maintained patches to generated copies, never to third_party sources."""
from pathlib import Path
import shutil
import subprocess

def prepare(root):
    target=root/'build/sitl-overrides'
    target.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/'third_party/ardupilot/libraries/SITL/SIM_JSBSim.cpp',target/'SIM_JSBSim.cpp')
    subprocess.run(['git','apply','--no-index','--directory=build/sitl-overrides','patches/jsbsim-absolute-altitude.patch'],cwd=root,check=True)
    return target

if __name__=='__main__':prepare(Path(__file__).resolve().parents[1])
