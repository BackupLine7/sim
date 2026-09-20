"""User airframes based on an installed, working flight model."""
import json
import math
import uuid
import base64
import struct
from copy import deepcopy


def create_aircraft(catalog, data):
    name=data.get('name','').strip()
    if not name:raise ValueError('Укажите название самолёта')
    aircraft=deepcopy(catalog.get(data.get('base_id')))
    scale=data.get('scale',aircraft.get('visual',{}).get('scale',1))
    if type(scale) not in (float,int) or not math.isfinite(scale) or scale<=0:
        raise ValueError('Масштаб должен быть положительным числом')
    aircraft.update(id='custom-'+uuid.uuid4().hex,name=name,custom=True,base_id=aircraft['id'])
    aircraft['description']=data.get('description','') or 'Пользовательский самолёт на базе '+catalog.get(data['base_id'])['name']
    aircraft['visual']['scale']=scale
    encoded=data.get('glb_base64')
    if encoded:
        try:
            model=base64.b64decode(encoded,validate=True)
            magic,version,length=struct.unpack_from('<4sII',model)
            chunk_length,chunk_type=struct.unpack_from('<II',model,12)
            document=json.loads(model[20:20+chunk_length])
            if magic!=b'glTF' or version!=2 or length!=len(model) or chunk_type!=0x4e4f534a:
                raise ValueError()
            if any('uri' in item for key in ('buffers','images') for item in document.get(key,[])):
                raise ValueError()
        except (ValueError,TypeError,struct.error):
            raise ValueError('Нужен GLB 2.0 со встроенными текстурами и буферами') from None
        assets=catalog.root/'web/data/aircraft/custom'/aircraft['id']
        assets.mkdir(parents=True,exist_ok=True)
        (assets/'model.glb').write_bytes(model)
        (assets/'support.json').write_text(json.dumps({'support_points':[[0,0,0]]}))
        aircraft['visual']=dict(uri=f'/data/aircraft/custom/{aircraft["id"]}/model.glb',support_uri=f'/data/aircraft/custom/{aircraft["id"]}/support.json',scale=scale,origin_up_m=0)
    directory=catalog.root/'config/custom-aircraft'
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/(aircraft['id']+'.json')
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(aircraft,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    return aircraft
