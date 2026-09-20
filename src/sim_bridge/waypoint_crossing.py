"""Intersection of a short telemetry segment with a waypoint cylinder."""
import math


def crosses_waypoint(previous,current,point,tolerance):
    def local(sample):
        lat,lon,alt=sample
        return ((lon-point['longitude_deg'])*111320*math.cos(math.radians(point['latitude_deg'])),(lat-point['latitude_deg'])*111320,alt-point['altitude_relative_m'])
    a=local(previous);b=local(current);d=[b[i]-a[i] for i in range(3)]
    lo,hi=0.,1.
    if abs(d[2])<1e-9:
        if abs(a[2])>tolerance:return False
    else:
        low,high=sorted(((-tolerance-a[2])/d[2],(tolerance-a[2])/d[2]))
        lo=max(lo,low);hi=min(hi,high)
    if lo>hi:return False
    length=d[0]**2+d[1]**2
    t=max(lo,min(hi,-(a[0]*d[0]+a[1]*d[1])/length)) if length else lo
    return (a[0]+t*d[0])**2+(a[1]+t*d[1])**2<=point['radius_m']**2
