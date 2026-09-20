"""Explicit local flight check: restart, takeoff, then observe LOITER."""
import asyncio,json,time
from pathlib import Path
import websockets
async def main():
 records=[];pose={};stage='restart';last_print=0;start=time.monotonic();circle_start=None;generation=None
 async with websockets.connect('ws://127.0.0.1:8081') as ws:
  await ws.send(json.dumps({'type':'command','action':'restart','aircraft_id':'f16'}))
  while time.monotonic()-start<210:
   m=json.loads(await asyncio.wait_for(ws.recv(),10));now=time.monotonic()
   if m.get('type')=='error':print(m,flush=True)
   if 'altitude_agl_m' in m:pose=m
   if m.get('type')!='status':continue
   if stage=='restart' and m.get('restarting'):generation=m['generation']
   if stage=='restart' and now-start>20 and m.get('connected') and m.get('prearm_ready') and not m.get('restarting'):
    await ws.send(json.dumps({'type':'command','action':'takeoff'}));stage='takeoff';print('TAKEOFF',flush=True)
   if stage=='takeoff' and now-start>70 and pose.get('altitude_agl_m',0)>80 and abs(m.get('telemetry',{}).get('climb_m_s',99))<5:
    await ws.send(json.dumps({'type':'command','action':'loiter'}));stage='loiter';circle_start=now;print('LOITER',flush=True)
   t=m.get('telemetry',{});row={'elapsed':now-start,'stage':stage,'mode':m.get('mode'),'generation':m.get('generation'),'height':pose.get('altitude_agl_m'),'altitude_msl_m':pose.get('altitude_asl_m'),**{k:t.get(k) for k in ['pitch_deg','roll_deg','airspeed_m_s','climb_m_s','servo_2_pwm','throttle_pct']}};records.append(row)
   if now-last_print>10:
    print(row,flush=True);last_print=now
    Path('logs/f16-tuning-flight.json').write_text(json.dumps(records),encoding='utf-8')
   if circle_start and now-circle_start>100:break
   if generation is not None and stage!='restart' and m.get('generation')!=generation:print('UNEXPECTED RESET',flush=True);break
 Path('logs/f16-tuning-flight.json').write_text(json.dumps(records))
asyncio.run(main())
