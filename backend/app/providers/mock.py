from app.providers.base import GeocodingProvider, RoutingProvider, WeatherProvider, TerrainProvider
from app.schemas.analysis import Coordinate, Location, Weather, Terrain

KNOWN = {
    "guwahati": (26.1445, 91.7362), "shillong": (25.5788, 91.8933),
    "cherrapunji": (25.2702, 91.7323), "tura": (25.5142, 90.2021),
}

class MockGeocodingProvider(GeocodingProvider):
    async def geocode(self, query: str) -> Location:
        lat, lng = KNOWN.get(query.strip().lower(), (25.95, 91.65))
        return Location(name=query.strip().title(), coordinate=Coordinate(lat=lat, lng=lng))
    async def suggest(self, query: str) -> list[dict]:
        q = query.strip().lower()
        return [{"name": f"{k.title()} (demo)", "short": k.title(), "lat": v[0], "lon": v[1], "type": "demo", "state": None} for k, v in KNOWN.items() if q and k.startswith(q)]

class MockRoutingProvider(RoutingProvider):
    async def routes(self, source: Location, destination: Location) -> list[dict]:
        a, b = source.coordinate, destination.coordinate
        variants = [
            ("Route A · NH6 Direct", 99.4, 172, -0.045, 60),
            ("Route B · Ridge Alternative", 108.8, 194, 0.075, 84),
            ("Route C · Eastern Bypass", 116.2, 211, 0.14, 72),
        ]
        rows=[]
        for i,(name,dist,dur,bend,quality) in enumerate(variants,1):
            geometry=[]
            for step in range(9):
                t=step/8
                geometry.append(Coordinate(lat=a.lat+(b.lat-a.lat)*t+bend*4*t*(1-t), lng=a.lng+(b.lng-a.lng)*t+bend*1.7*4*t*(1-t)))
            names=["NH27","NH6","Umiam bypass","NH6 (Shillong approach)"]
            directions=[{"instruction":"Depart Guwahati depot","road":"GS Road","distance_m":2400,"duration_s":420,"location":geometry[0].model_dump(),"maneuver":"depart"}]+[{"instruction":f"Continue on {names[k%len(names)]}","road":names[k%len(names)],"distance_m":round(dist*1000/8),"duration_s":round(dur*60/8),"location":geometry[k+1].model_dump(),"maneuver":"continue"} for k in range(7)]+[{"instruction":"Arrive at destination","road":"","distance_m":0,"duration_s":0,"location":geometry[-1].model_dump(),"maneuver":"arrive"}]
            rows.append({"id":f"route-{i}","name":name,"distance_km":dist,"duration_minutes":dur,"geometry":geometry,"road_quality":quality,"variant":i,"directions":directions})
        return rows

class MockWeatherProvider(WeatherProvider):
    async def weather_for_route(self, route: dict) -> Weather:
        v=route["variant"]
        return Weather(temperature_c=19-v, rainfall_mm=[28,8,14][v-1], rainfall_probability=[88,42,61][v-1], humidity=82, wind_kph=13, visibility_km=[3.8,8.4,6.2][v-1], condition=["Heavy rain","Light showers","Intermittent rain"][v-1])

class MockTerrainProvider(TerrainProvider):
    async def terrain_for_route(self, route: dict) -> Terrain:
        v=route["variant"]
        return Terrain(elevation_m=[1540,1320,1460][v-1], average_slope=[14.8,7.2,10.1][v-1], classification=["Steep mountain","Rolling highland","Mountain road"][v-1])

