from abc import ABC, abstractmethod
from app.schemas.analysis import Location, RouteResult, Weather, Terrain

class GeocodingProvider(ABC):
    @abstractmethod
    async def geocode(self, query: str) -> Location: ...

class RoutingProvider(ABC):
    @abstractmethod
    async def routes(self, source: Location, destination: Location) -> list[dict]: ...

class WeatherProvider(ABC):
    @abstractmethod
    async def weather_for_route(self, route: dict) -> Weather: ...

class TerrainProvider(ABC):
    @abstractmethod
    async def terrain_for_route(self, route: dict) -> Terrain: ...

