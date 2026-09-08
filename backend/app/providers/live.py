import asyncio,hashlib
import httpx
from app.core.config import get_settings
from app.providers.base import GeocodingProvider,RoutingProvider,WeatherProvider,TerrainProvider
from app.schemas.analysis import Coordinate,DirectionStep,Location,Terrain,Weather
from app.services.cache import get_cache
from app.utils.geo import sample_fixed,elevation_metrics
class NominatimGeocodingProvider(GeocodingProvider):
    """Nominatim with a North-East India viewbox bias, suffix fallbacks and a shared 24 h cache (usage policy: cached, custom UA)."""
    HEADERS={"User-Agent":"PathSense/1.0 logistics-research (contact: three-dteam@pw.live)"}
    async def search(self,query:str,limit:int=3)->list[dict]:
        from app.core.domain import GEOCODE_VIEWBOX
        settings=get_settings();vb=GEOCODE_VIEWBOX
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds,headers=self.HEADERS) as client:
            response=await client.get(f"{settings.nominatim_base_url}/search",params={"q":query,"format":"jsonv2","limit":limit,"countrycodes":"in","viewbox":f"{vb[0]},{vb[3]},{vb[2]},{vb[1]}","bounded":0,"addressdetails":1});response.raise_for_status();return response.json()
    @staticmethod
    def rank(rows:list[dict])->list[dict]:
        from app.core.domain import GEOCODE_VIEWBOX
        vb=GEOCODE_VIEWBOX
        inside=lambda r:vb[0]<=float(r["lon"])<=vb[2] and vb[1]<=float(r["lat"])<=vb[3]
        return sorted(rows,key=lambda r:(not inside(r),-float(r.get("importance",0))))
    async def geocode(self,query:str)->Location:
        from app.core.domain import GEOCODE_FALLBACK_SUFFIXES
        query=query.strip()
        key="geocode:"+hashlib.sha256(query.lower().encode()).hexdigest();cache=get_cache()
        if hit:=await cache.get(key):return Location.model_validate(hit)
        rows=[]
        for candidate in [query]+[query+suffix for suffix in GEOCODE_FALLBACK_SUFFIXES]:
            rows=self.rank(await self.search(candidate))
            if rows:break
        if not rows:raise ValueError(f"Location not found: '{query}'. Try a town or district name, e.g. 'Tezpur, Assam'.")
        row=rows[0];result=Location(name=row.get("display_name",query),coordinate=Coordinate(lat=float(row["lat"]),lng=float(row["lon"])))
        await cache.set(key,result.model_dump(),86400);return result
    async def suggest(self,query:str)->list[dict]:
        from app.core.domain import GEOCODE_SUGGEST_LIMIT
        query=query.strip()
        if len(query)<3:return []
        key="suggest:"+hashlib.sha256(query.lower().encode()).hexdigest();cache=get_cache()
        if (hit:=await cache.get(key)) is not None:return hit
        rows=self.rank(await self.search(query,GEOCODE_SUGGEST_LIMIT))
        out=[{"name":r.get("display_name"),"short":(r.get("address") or {}).get("city") or (r.get("address") or {}).get("town") or (r.get("address") or {}).get("village") or r.get("name") or r.get("display_name","").split(",")[0],"lat":float(r["lat"]),"lon":float(r["lon"]),"type":r.get("type"),"state":(r.get("address") or {}).get("state")} for r in rows]
        await cache.set(key,out,86400);return out
class OSRMRoutingProvider(RoutingProvider):
    async def routes(self,source:Location,destination:Location)->list[dict]:
        s,d=source.coordinate,destination.coordinate;settings=get_settings();coords=f"{s.lng},{s.lat};{d.lng},{d.lat}"
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
            response=await client.get(f"{settings.osrm_base_url}/route/v1/driving/{coords}",params={"overview":"full","geometries":"geojson","alternatives":"3","steps":"true"});response.raise_for_status();payload=response.json()
        if payload.get("code")!="Ok":raise RuntimeError(payload.get("message","Routing unavailable"))
        return [{"id":f"osrm-{i+1}","name":f"Route {chr(65+i)}", "distance_km":round(r["distance"]/1000,1),"duration_minutes":round(r["duration"]/60),"geometry":[Coordinate(lat=p[1],lng=p[0]) for p in r["geometry"]["coordinates"]],"road_quality":70,"variant":i+1,"legs":[],"directions":osrm_directions(r)} for i,r in enumerate(payload["routes"])]
MANEUVER_TEXT={"depart":"Depart","arrive":"Arrive at destination","turn":"Turn","new name":"Continue onto","continue":"Continue","merge":"Merge","on ramp":"Take the ramp","off ramp":"Take the exit","fork":"Keep","end of road":"At the end of the road turn","roundabout":"At the roundabout take exit","rotary":"At the rotary take exit","roundabout turn":"At the roundabout turn","notification":"Continue","exit roundabout":"Exit the roundabout","exit rotary":"Exit the rotary"}
def osrm_directions(route:dict,limit:int=80)->list[DirectionStep]:
    """Compact turn-by-turn steps from OSRM legs (no provider re-run; stored with the analysis)."""
    steps=[]
    for leg in route.get("legs",[]):
        for st in leg.get("steps",[]):
            m=st.get("maneuver",{});kind=m.get("type","");mod=m.get("modifier","");road=st.get("name") or st.get("ref") or ""
            base=MANEUVER_TEXT.get(kind,kind.replace("_"," ").capitalize() or "Continue")
            if kind in{"roundabout","rotary"} and m.get("exit"):base=f"{base} {m['exit']}"
            text=base+(f" {mod}" if mod and kind not in{"depart","arrive","new name","continue","notification"} else "")+(f" onto {road}" if road and kind not in{"arrive","new name","continue","notification"} else f" on {road}" if road and kind in{"continue","notification"} else f" {road}" if road and kind=="new name" else "")
            loc=m.get("location");steps.append(DirectionStep(instruction=text.strip(),road=road,distance_m=round(st.get("distance",0)),duration_s=round(st.get("duration",0)),location=Coordinate(lat=loc[1],lng=loc[0]) if loc else None,maneuver=f"{kind} {mod}".strip()))
            if len(steps)>=limit:return steps
    return steps
class OpenWeatherProvider(WeatherProvider):
    async def _point(self,p:Coordinate):
        settings=get_settings();key=f"weather:{p.lat:.3f}:{p.lng:.3f}";cache=get_cache()
        if hit:=await cache.get(key):return hit
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
            r=await client.get("https://api.openweathermap.org/data/2.5/weather",params={"lat":p.lat,"lon":p.lng,"appid":settings.openweather_api_key,"units":"metric"});r.raise_for_status();data=r.json()
        normalized={"temperature":data["main"]["temp"],"rain":data.get("rain",{}).get("1h",0),"humidity":data["main"]["humidity"],"visibility":data.get("visibility",10000)/1000,"wind":data.get("wind",{}).get("speed",0)*3.6,"condition":data["weather"][0]["description"]};await cache.set(key,normalized,900);return normalized
    async def weather_for_route(self,route:dict)->Weather:
        results=await asyncio.gather(*(self._point(p) for p in sample_fixed(route["geometry"],5)),return_exceptions=True);ok=[r for r in results if isinstance(r,dict)]
        if not ok:raise RuntimeError("Weather unavailable")
        worst=max(ok,key=lambda x:x["rain"]+max(0,5-x["visibility"])*2)
        return Weather(temperature_c=round(sum(x["temperature"] for x in ok)/len(ok),1),rainfall_mm=max(x["rain"] for x in ok),rainfall_probability=0,humidity=round(sum(x["humidity"] for x in ok)/len(ok)),wind_kph=max(x["wind"] for x in ok),visibility_km=round(sum(x["visibility"] for x in ok)/len(ok),1),condition=worst["condition"],data_status="live")
class OpenElevationTerrainProvider(TerrainProvider):
    async def terrain_for_route(self,route:dict)->Terrain:
        points=sample_fixed(route["geometry"],10);payload={"locations":[{"latitude":p.lat,"longitude":p.lng} for p in points]}
        async with httpx.AsyncClient(timeout=get_settings().provider_timeout_seconds) as client:r=await client.post("https://api.open-elevation.com/api/v1/lookup",json=payload);r.raise_for_status();e=[x["elevation"] for x in r.json()["results"]]
        metrics=elevation_metrics(e,points);slope=metrics["maximum_estimated_slope"]
        return Terrain(elevation_m=metrics["average_elevation"],average_slope=slope,classification="steep mountain" if slope>=12 else "mountain" if slope>=7 else "rolling terrain",data_status="estimated")
