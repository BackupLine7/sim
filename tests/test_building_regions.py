import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sim_world.buildings.regions import BuildingRegions
from sim_world import tile_xy


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchmany(self, count):
        result, self.rows = self.rows[:count], self.rows[count:]
        return result


class RegionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        project = Path(__file__).resolve().parents[1]
        for name in ('building-regions.json', 'world.json'):
            shutil.copy(project/'config'/name, self.root/'config'/name)
        self.store = BuildingRegions(self.root)
        self.region = dict(id='test-region', name='Test', country='UA', code='UA-test', bounds=[33,44,35,46],
                           geometry={'type':'Polygon','coordinates':[[[33,44],[35,44],[35,46],[33,46],[33,44]]]})
        self.store.regions = {'test-region':self.region}
        self.store.jobs['test-region'] = dict(state='loading')

    def tearDown(self):
        self.store.pool.shutdown(wait=True)
        self.temp.cleanup()

    def test_pack_reopens_offline_and_serves_only_its_tile_with_holes(self):
        outer = [[34,45],[34.001,45],[34.001,45.001],[34,45]]
        hole = [[34.0002,45.0001],[34.0003,45.0001],[34.0003,45.0002],[34.0002,45.0001]]
        cursor = Cursor([('one',15,json.dumps(dict(type='Polygon',coordinates=[outer,hole])))])
        count = self.store._write_pack(self.store.directory/'test-region.sqlite', cursor, self.region)
        self.assertEqual(count,1)
        with patch.object(BuildingRegions,'_connect',side_effect=AssertionError('network used')):
            offline = BuildingRegions(self.root)
            level=offline.world['detail_level']
            x,y = tile_xy(34,45,level)
            buildings = offline.buildings(level,x,y)
            self.assertEqual(len(buildings),1)
            self.assertEqual(buildings[0]['height_m'],15)
            self.assertEqual(buildings[0]['holes'],[hole])
            self.assertEqual(offline.buildings(level,x+1,y),[])
            self.assertEqual(offline.buildings(level-1,x//2,y//2),[])
            offline.pool.shutdown()

    def test_failed_refresh_retains_previous_pack_and_revision(self):
        path=self.store.directory/'test-region.sqlite'
        path.write_bytes(b'previous pack')
        revision=self.store.revision
        job=dict(state='queued')
        self.store.jobs['test-region']=job
        with patch.object(self.store,'_connect',side_effect=OSError('offline')):
            self.store._download('test-region',job)
        self.assertEqual(path.read_bytes(),b'previous pack')
        self.assertEqual(self.store.revision,revision)
        self.assertEqual(job['state'],'error')
        self.assertFalse(path.with_suffix('.partial').exists())

    def test_cancelled_queued_job_cannot_consume_replacement_job(self):
        old=dict(state='cancelled');new=dict(state='queued')
        self.store.jobs['test-region']=new
        with patch.object(self.store,'_connect',side_effect=AssertionError('network used')):
            self.store._download('test-region',old)
        self.assertEqual(new['state'],'queued')

    def test_unknown_region_rejected(self):
        with self.assertRaises(ValueError):
            self.store.download('../../outside')

    def test_bundled_list_includes_all_ukrainian_regions_without_network(self):
        project = Path(__file__).resolve().parents[1]
        shutil.copy(project/'config/building-region-catalog.json', self.root/'config/building-region-catalog.json')
        with patch('urllib.request.urlopen', side_effect=AssertionError('network used')):
            offline = BuildingRegions(self.root)
            status = offline.status()
            self.assertEqual(status['state'],'ready')
            ukrainian = [r for r in status['regions'] if r['country']=='UA']
            self.assertEqual(len(ukrainian),27)
            self.assertEqual(status['regions'][:27],ukrainian)
            self.assertIn('Херсонская область',[r['name'] for r in ukrainian])
            self.assertIn('АР Крым',[r['name'] for r in ukrainian])
            offline.pool.shutdown()

    def test_boundary_uses_cached_country_and_exact_feature(self):
        geometry = self.region['geometry']
        (self.store.directory/'boundary-UKR.json').write_text(json.dumps(dict(features=[
            dict(properties=dict(shapeID='other'),geometry=None),
            dict(properties=dict(shapeID='wanted'),geometry=geometry)])))
        region=dict(boundary_country='UKR',boundary_id='wanted')
        with patch('urllib.request.urlopen', side_effect=AssertionError('network used')):
            self.assertEqual(self.store._boundary(region)['geometry'],geometry)
