"""Shared geographic mission catalog for rendering and flight guidance."""
import json
import math
import re
import uuid
import os
import tempfile
from pathlib import Path


class MissionStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def read(self):
        missions, errors = [], []
        for path in sorted(self.directory.glob('*.json')):
            try:
                mission = json.loads(path.read_text(encoding='utf-8'))
                self.validate(mission)
                missions.append(dict(mission, id=path.stem))
            except (ValueError, TypeError, KeyError, OSError) as error:
                errors.append(f'{path.name}: {error}')
        return {'missions': missions, 'errors': errors}

    def delete(self, mission_id):
        root = self.directory.parent.parent
        if not any(m['id'] == mission_id for m in self.catalog(root)['missions']):
            raise ValueError('Миссия не найдена')
        path = self.directory.parent/'local.missions-deleted.json'
        deleted = json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        from .start_locations import StartLocations
        StartLocations.write(path, deleted+[mission_id])
        return dict(deleted_id=mission_id)

    def save(self, mission, mission_id=None):
        for point in mission.get('waypoints', []):
            if isinstance(point, dict) and point.get('type') == 'goal':
                point['altitude_relative_m'] = 0
                point.pop('terrain_elevation_asl_m', None)
        self.validate(mission)
        for point in mission['waypoints']:
            if point.get('type', 'transit') not in ('transit', 'goal', 'land'):
                raise ValueError('Неизвестный тип точки')
        if mission_id is None:
            mission_id = 'custom-' + uuid.uuid4().hex
        if not isinstance(mission_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', mission_id) or mission_id.startswith('training-'):
            raise ValueError('Недопустимый идентификатор миссии')
        self.directory.mkdir(parents=True, exist_ok=True)
        value = {k:v for k,v in mission.items() if k not in ('id', 'coordinate_system')}
        descriptor, temporary = tempfile.mkstemp(dir=self.directory, suffix='.tmp')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
            os.replace(temporary, self.directory / (mission_id + '.json'))
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
        return dict(value, id=mission_id)

    @classmethod
    def catalog(cls, root):
        result = cls(root / 'config' / 'missions').read()
        session = json.loads((root / 'web/data/session.json').read_text(encoding='utf-8'))
        defaults = json.loads((root / 'config/mission-navigation.json').read_text(encoding='utf-8'))
        result['defaults'] = defaults
        for mission in result['missions']:
            for point in mission['waypoints']:
                point.setdefault('altitude_relative_m', session['airfield']['takeoff_altitude_m'])
                point.setdefault('radius_m', defaults['radius_m'])
            mission.setdefault('height_tolerance_m', defaults['height_tolerance_m'])
        lessons = json.loads((root / 'config/training-lessons.json').read_text(encoding='utf-8'))['lessons']
        longitude_deg, latitude_deg = session['home']
        for lesson in lessons:
            points = []
            for point in lesson['waypoints']:
                # Local lesson axes: east/north, anchored at the current airfield.
                east_m = point['x_m'] - lesson['start']['x_m']
                north_m = point['y_m'] - lesson['start']['y_m']
                distance_m = math.hypot(east_m, north_m)
                bearing_rad = math.atan2(east_m, north_m)
                angular_distance = distance_m / 6378137.0
                latitude_rad = math.radians(latitude_deg)
                target_latitude = math.asin(math.sin(latitude_rad)*math.cos(angular_distance) + math.cos(latitude_rad)*math.sin(angular_distance)*math.cos(bearing_rad))
                target_longitude = math.radians(longitude_deg) + math.atan2(math.sin(bearing_rad)*math.sin(angular_distance)*math.cos(latitude_rad), math.cos(angular_distance)-math.sin(latitude_rad)*math.sin(target_latitude))
                points.append(dict(point, latitude_deg=math.degrees(target_latitude), longitude_deg=(math.degrees(target_longitude)+180)%360-180, altitude_relative_m=point['height_m']))
            result['missions'].append(dict(lesson, id='training-' + lesson['id'], coordinate_system='geographic', waypoints=points))
        deleted_path = root/'config/local.missions-deleted.json'
        deleted = json.loads(deleted_path.read_text(encoding='utf-8')) if deleted_path.exists() else []
        result['missions'] = [m for m in result['missions'] if m['id'] not in deleted]
        for mission in result['missions']:
            cls.validate(mission)
            mission['route_render_step_m']=defaults['route_render_step_m']
        return result

    @staticmethod
    def validate(mission):
        if not isinstance(mission, dict) or not isinstance(mission.get('name'), str) or not mission['name'].strip():
            raise ValueError('Укажите название миссии')
        points = mission.get('waypoints')
        if not isinstance(points, list) or not 2 <= len(points) <= 1000:
            raise ValueError('Нужно от 2 до 1000 точек')
        for point in points:
            if not isinstance(point, dict):
                raise ValueError('Точка должна быть объектом')
            for key, limit in [('latitude_deg', 90), ('longitude_deg', 180)]:
                value = point.get(key)
                if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit:
                    raise ValueError(f'Некорректная координата {key}')
            for key in ('altitude_relative_m', 'radius_m'):
                if key in point and (type(point[key]) not in (int, float) or not math.isfinite(point[key]) or (point[key] <= 0 and not (key == 'altitude_relative_m' and point.get('type') == 'goal'))):
                    raise ValueError(f'Некорректное значение {key}')
        if 'height_tolerance_m' in mission:
            value = mission['height_tolerance_m']
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('Некорректный допуск высоты')
