"""Persistent start locations; selection takes effect only on explicit restart."""
import json
import math
import uuid
from pathlib import Path
import yaml

class StartLocations:
    def __init__(self, root):
        self.root=Path(root)
        self.path=self.root/'config/local.starts.json'
        self.active_path=self.root/'config/local.start-active.json'

    def catalog(self):
        polygon=yaml.safe_load((self.root/'config/simulation.yaml').read_text(encoding='utf-8'))['polygon']
        default=dict(id='default',name='Исходная площадка',latitude_deg=polygon['home_latitude_deg'],longitude_deg=polygon['home_longitude_deg'],elevation_asl_m=polygon['home_elevation_asl_m'],heading_deg=polygon['home_heading_deg'])
        locations=[default]+(json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else [])
        active=json.loads(self.active_path.read_text(encoding='utf-8'))['id'] if self.active_path.exists() else 'default'
        return dict(locations=locations,active_id=active)

    def find(self, identifier):
        for location in self.catalog()['locations']:
            if location['id']==identifier:return location
        raise ValueError('Точка старта не найдена')

    def save(self, data):
        if not isinstance(data,dict):raise ValueError('Неверная точка старта')
        name=data.get('name')
        if not isinstance(name,str) or not name.strip() or len(name)>120:raise ValueError('Введите название до 120 символов')
        for key in ('latitude_deg','longitude_deg','elevation_asl_m','heading_deg'):
            value=data.get(key)
            if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Координаты, высота и курс должны быть конечными числами')
        if not -90<data['latitude_deg']<90 or not -180<=data['longitude_deg']<=180 or not 0<=data['heading_deg']<360:raise ValueError('Некорректные координаты или курс')
        location={key:data[key] for key in ('latitude_deg','longitude_deg','elevation_asl_m','heading_deg')}
        identifier=data.get('id')
        if identifier is not None:
            if identifier=='default':raise ValueError('Исходная площадка доступна только для чтения')
            self.find(identifier)
        location.update(id=identifier or uuid.uuid4().hex,name=name.strip())
        locations=self.catalog()['locations'][1:]
        if identifier is None:locations.append(location)
        else:locations=[location if point['id']==identifier else point for point in locations]
        self.write(self.path,locations)
        return location

    def delete(self, identifier):
        if identifier == 'default':
            raise ValueError('Исходную площадку удалить нельзя')
        location = self.find(identifier)
        archive = self.root/'config/local.starts-deleted.json'
        deleted = json.loads(archive.read_text(encoding='utf-8')) if archive.exists() else []
        self.write(archive, deleted+[location])
        self.write(self.path, [p for p in self.catalog()['locations'][1:] if p['id'] != identifier])
        # The active snapshot remains valid until the next explicit flight reset.
        return dict(deleted_id=identifier)

    def activate(self, identifier):
        location=self.find(identifier)
        self.write(self.active_path,location)
        return location

    @staticmethod
    def write(path, value):
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        temporary.replace(path)
