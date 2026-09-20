"""Extract lower support vertices from the displayed GLB for ground alignment."""
import json,struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
data=(ROOT/'web/data/aircraft.glb').read_bytes();length=struct.unpack_from('<I',data,12)[0];gltf=json.loads(data[20:20+length]);binary=data[28+length:]
points=[]
def positions(index):
 accessor=gltf['accessors'][index];view=gltf['bufferViews'][accessor['bufferView']]
 assert accessor['componentType']==5126 and accessor['type']=='VEC3'
 return np.ndarray((accessor['count'],3),dtype='<f4',buffer=binary,offset=view.get('byteOffset',0)+accessor.get('byteOffset',0),strides=(view.get('byteStride',12),4)).astype(float)
def visit(index,parent):
 node=gltf['nodes'][index]
 if 'matrix' in node:local=np.array(node['matrix']).reshape(4,4).T
 else:
  x,y,z,w=node.get('rotation',[0,0,0,1]);local=np.eye(4)
  local[:3,:3]=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])@np.diag(node.get('scale',[1,1,1]))
  local[:3,3]=node.get('translation',[0,0,0])
 matrix=parent@local
 if 'mesh' in node:
  for primitive in gltf['meshes'][node['mesh']]['primitives']:
   p=positions(primitive['attributes']['POSITION']);points.append(p@matrix[:3,:3].T+matrix[:3,3])
 for child in node.get('children',[]):visit(child,matrix)
for node in gltf['scenes'][gltf.get('scene',0)]['nodes']:visit(node,np.eye(4))
p=np.unique(np.concatenate(points),axis=0)[:,[2,0,1]] # Cesium Y-up/Z-forward -> body X-forward/Z-up.
selected=set()
for pitch in range(-30,31,2):
 for roll in range(-30,31,2):
  theta,phi=np.radians([pitch,roll]);direction=[np.sin(theta),np.cos(theta)*np.sin(phi),np.cos(theta)*np.cos(phi)]
  selected.add(int(np.argmin(p@direction)))
result={'support_points':p[sorted(selected)].round(7).tolist(),'pitch_limit_deg':30,'roll_limit_deg':30}
(ROOT/'web/data/aircraft-support.json').write_text(json.dumps(result),encoding='utf-8')
print(f'{len(p)} mesh vertices -> {len(selected)} lower support vertices')
