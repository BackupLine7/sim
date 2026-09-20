import gzip
import json
import math
import re
import threading
import time
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

_instances={}
_instances_lock=threading.Lock()

def terrain_cache(root):
    root=Path(root).resolve()
    with _instances_lock:
        if root not in _instances:_instances[root]=TerrainCache(root)
        return _instances[root]

def tile_name(lat,lon):
    lat,lon=math.floor(lat),math.floor(lon)
    return f"{'N' if lat>=0 else 'S'}{abs(lat):02d}{'E' if lon>=0 else 'W'}{abs(lon):03d}"

class TerrainCache:
    def __init__(self,root):
        self.root=Path(root)
        self.settings=json.loads((self.root/'config/terrain-streaming.json').read_text())
        self.directory=(self.root/self.settings['cache_directory']).resolve()
        if self.directory==self.root.resolve() or not self.directory.is_relative_to(self.root.resolve()):raise ValueError('Кеш высот должен находиться внутри проекта')
        self.directory.mkdir(parents=True,exist_ok=True)
        self.enabled=self.settings['enabled']
        self.preference_path=self.root/'config/local.terrain-streaming.json'
        if self.preference_path.exists():self.enabled=json.loads(self.preference_path.read_text())['enabled']
        self.tiles=OrderedDict()
        self.pending=set();self.retry={};self.suppressed=set();self.errors={}
        self.lock=threading.RLock()
        self.pool=ThreadPoolExecutor(max_workers=self.settings['parallel_downloads'],thread_name_prefix='terrain-download')
        self.position=None;self.airborne=False;self.generation=None;self.revision=0
        self.active=set();self.last_region=None

    def observe(self,pose):
        generation=pose.get('generation',0)
        with self.lock:
            if self.generation!=generation:
                self.generation=generation
                self.suppressed.clear()

                self.tiles=OrderedDict((key,(value[0],None)) for key,value in self.tiles.items())
                self.revision+=1
            self.position=(pose['latitude_deg'],pose['longitude_deg'])
            self.airborne=pose['altitude_agl_m']>self.settings['airborne_height_m']
            lat,lon=map(math.floor,self.position);radius=self.settings['radius_degrees']
            keys=[(lat+y,lon+x) for y in range(-radius,radius+1) for x in range(-radius,radius+1) if -90<lat+y<90 and -180<=lon+x<180]
            keys.sort(key=lambda point:abs(point[0]-lat)+abs(point[1]-lon))
            self.active={tile_name(*point) for point in keys}
            for point in keys:self.request(*point)

    def request(self,lat,lon):
        key=tile_name(lat,lon)
        if key in self.tiles or key in self.pending or key in self.suppressed or time.monotonic()<self.retry.get(key,0):return
        if len(self.pending)>=self.settings['maximum_memory_tiles']:return
        if not self.enabled and not (self.directory/(key+'.hgt')).exists():return
        self.pending.add(key)
        self.pool.submit(self.load,key)

    def load(self,key):
        path=self.directory/(key+'.hgt')
        try:
            if path.exists():raw=path.read_bytes()
            else:
                if not self.enabled:return
                url=self.settings['url_template'].format(latitude=key[:3],tile=key)
                with urllib.request.urlopen(url,timeout=self.settings['timeout_s']) as response:
                    compressed=response.read(3601*3601*2+1)
                raw=gzip.decompress(compressed)
            side=math.isqrt(len(raw)//2)
            if side not in (1201,3601) or len(raw)!=side*side*2:
                if path.exists():path.unlink()
                raise ValueError('Неверный размер HGT')
            array=np.frombuffer(raw,dtype='>i2').reshape(side,side)
            with self.lock:
                if not path.exists():
                    temporary=path.with_suffix('.tmp');temporary.write_bytes(raw);temporary.replace(path)
                protection=self.position if self.airborne else None
                self.tiles[key]=(array,protection)
                while len(self.tiles)>self.settings['maximum_memory_tiles']:
                    victim=next((name for name in self.tiles if name not in self.active),None)
                    if victim is None:break
                    del self.tiles[victim]
                self.revision+=1;self.errors.pop(key,None)
                self.trim_disk()
        except Exception as error:
            with self.lock:self.errors[key]=str(error);self.retry[key]=time.monotonic()+self.settings['retry_s']
        finally:
            with self.lock:self.pending.discard(key)

    def sample(self,lat,lon,fallback,*,protect_flight=True):
        with self.lock:
            entry=self.tiles.get(tile_name(lat,lon))
        if entry is None:return fallback
        data,protection=entry;n=data.shape[0]-1
        x=(lon-math.floor(lon))*n;y=(math.floor(lat)+1-lat)*n
        col=min(n-1,max(0,int(x)));row=min(n-1,max(0,int(y)))
        a,b,c,d=map(float,(data[row,col],data[row,col+1],data[row+1,col],data[row+1,col+1]))
        if min(a,b,c,d)==-32768:return fallback
        fx=x-col;fy=y-row;value=(a*(1-fx)+b*fx)*(1-fy)+(c*(1-fx)+d*fx)*fy
        if protection and protect_flight:
            north=(lat-protection[0])*111320;east=(lon-protection[1])*111320*math.cos(math.radians(lat))
            blend=min(1,max(0,(math.hypot(north,east)-self.settings['activation_radius_m'])/self.settings['activation_blend_m']))
            blend=blend*blend*(3-2*blend);value=fallback+(value-fallback)*blend
        return value

    def files(self):
        return [p for p in self.directory.glob('*.hgt') if re.fullmatch(r'[NS]\d{2}[EW]\d{3}\.hgt',p.name) and not p.is_symlink() and p.resolve().parent==self.directory]

    def trim_disk(self):
        files=sorted(self.files(),key=lambda p:p.stat().st_mtime)
        total=sum(p.stat().st_size for p in files)
        for path in files:
            if total<=self.settings['disk_limit_mb']*1024**2:break
            if path.stem in self.active:continue
            total-=path.stat().st_size;path.unlink()

    def clear(self):
        with self.lock:
            if self.pending:raise ValueError('Дождитесь завершения загрузки перед очисткой кеша')
            files=self.files();removed=sum(p.stat().st_size for p in files)
            for path in files:path.unlink()
            self.suppressed.update(self.active)
            return removed

    def status(self):
        with self.lock:
            files=self.files()
            return dict(enabled=self.enabled,revision=self.revision,files=len(files),disk_mb=round(sum(p.stat().st_size for p in files)/1024**2,1),memory_tiles=len(self.tiles),pending=len(self.pending),errors=dict(self.errors))

    def set_enabled(self,enabled):
        with self.lock:
            self.enabled=enabled
            temporary=self.preference_path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'enabled':enabled}));temporary.replace(self.preference_path)