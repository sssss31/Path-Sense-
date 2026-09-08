from math import asin,cos,radians,sin,sqrt
from app.schemas.analysis import Coordinate
def distance_km(a:Coordinate,b:Coordinate)->float:
    dlat=radians(b.lat-a.lat);dlon=radians(b.lng-a.lng)
    h=sin(dlat/2)**2+cos(radians(a.lat))*cos(radians(b.lat))*sin(dlon/2)**2
    return 6371*2*asin(sqrt(h))
def sample_fixed(points:list[Coordinate],count:int=5)->list[Coordinate]:
    if len(points)<=count:return points
    return [points[round(i*(len(points)-1)/(count-1))] for i in range(count)]
def sample_every_km(points:list[Coordinate],spacing_km:float)->list[Coordinate]:
    if not points:return []
    out=[points[0]];acc=0.0
    for a,b in zip(points,points[1:]):
        acc+=distance_km(a,b)
        if acc>=spacing_km:out.append(b);acc=0
    if out[-1]!=points[-1]:out.append(points[-1])
    return out
def elevation_metrics(elevations:list[float],points:list[Coordinate])->dict:
    gains=sum(max(0,b-a) for a,b in zip(elevations,elevations[1:]));slopes=[]
    for i,(a,b) in enumerate(zip(elevations,elevations[1:])):
        run=max(distance_km(points[i],points[i+1])*1000,1);slopes.append(abs(b-a)/run*100)
    return {"minimum_elevation":round(min(elevations)),"maximum_elevation":round(max(elevations)),"average_elevation":round(sum(elevations)/len(elevations)),"elevation_gain":round(gains),"maximum_estimated_slope":round(max(slopes,default=0),1)}
