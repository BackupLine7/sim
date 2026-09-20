"""Generate lightweight, schematic airframe meshes (metres, glTF Y-up)."""
import json, math, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(name,length,span,jet):
    vertices=[];normals=[]
    def triangle(a,b,c):
        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        mag=math.sqrt(sum(x*x for x in n)) or 1
        vertices.extend([a,b,c]);normals.extend([[x/mag for x in n]]*3)
    def panel(points):
        for i in range(1,len(points)-1):triangle(points[0],points[i],points[i+1])
    rings=[(-.5,0.12),(-.3,.38),(0,.48),(.28,.4),(.5,.015)]
    for (z,r),(zz,rr) in zip(rings,rings[1:]):
        for i in range(16):
            a=i*math.tau/16;b=(i+1)*math.tau/16
            p=(r*math.cos(a),r*math.sin(a),z*length);q=(r*math.cos(b),r*math.sin(b),z*length)
            t=(rr*math.cos(b),rr*math.sin(b),zz*length);w=(rr*math.cos(a),rr*math.sin(a),zz*length)
            triangle(p,q,t);triangle(p,t,w)
    y=0 if jet else .48
    for side in (-1,1):
        panel([(side*.2,y,length*.12),(side*span/2,y,-length*(.12 if jet else -.08)),(side*span/2,y,-length*.22),(side*.2,y,-length*.2)])
        panel([(0,.1,-length*.3),(side*span*.22,.1,-length*.41),(side*span*.22,.1,-length*.49),(0,.1,-length*.46)])
    panel([(0,.1,-length*.23),(0,length*.17,-length*.4),(0,length*.17,-length*.48),(0,.1,-length*.49)])
    # Canopy gives the schematic aircraft a recognisable cockpit silhouette.
    panel([(-.32,.3,length*.24),(0,.85,length*.13),(.32,.3,length*.24)])
    panel([(-.32,.3,length*.24),(-.32,.3,-length*.02),(0,.85,length*.13)])
    panel([(.32,.3,length*.24),(0,.85,length*.13),(.32,.3,-length*.02)])
    if not jet:
        panel([(-span*.12,0,length*.49),(span*.12,0,length*.49),(span*.12,.08,length*.49),(-span*.12,.08,length*.49)])
    raw=b''.join(struct.pack('<3f',*v) for v in vertices+normals)
    size=len(vertices)*12
    gltf={'asset':{'version':'2.0','generator':'Flight Lab schematic airframes'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],
      'buffers':[{'byteLength':len(raw)}], 'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':size},{'buffer':0,'byteOffset':size,'byteLength':size}],
      'accessors':[{'bufferView':0,'componentType':5126,'count':len(vertices),'type':'VEC3','min':[min(v[i] for v in vertices) for i in range(3)],'max':[max(v[i] for v in vertices) for i in range(3)]},{'bufferView':1,'componentType':5126,'count':len(normals),'type':'VEC3'}],
      'materials':[{'doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[.45,.52,.58,1] if jet else [.9,.87,.72,1],'metallicFactor':.1,'roughnessFactor':.65}}],
      'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1},'material':0}]}]}
    header=json.dumps(gltf,separators=(',',':')).encode();header+=b' '*((-len(header))%4)
    data=struct.pack('<III',0x46546c67,2,28+len(header)+len(raw))+struct.pack('<II',len(header),0x4e4f534a)+header+struct.pack('<II',len(raw),0x004e4942)+raw
    folder=ROOT/'web/data/aircraft';folder.mkdir(exist_ok=True)
    (folder/f'{name}.glb').write_bytes(data)
    (folder/f'{name}-support.json').write_text(json.dumps({'support_points':[[v[2],v[0],v[1]] for v in vertices]}))

if __name__=='__main__':
    build('c172p',8.28,11,False)
    build('f16',14.8,9.14,True)
