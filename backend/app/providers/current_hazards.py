"""Current-event hazard providers (interfaces only).

No verified real-time landslide, flood-event or road-closure feed is connected
yet, so every method returns an explicit ``unavailable`` state. Nothing here
may ever be inferred as "no hazard": unavailable means unknown.

Future implementations (official disaster alerts, PWD feeds, verified operator
reports) must set ``status="live"`` only for timestamped, currently active
observations.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone

def unavailable(kind: str, reason: str) -> dict:
    return {"kind": kind, "status": "unavailable", "events": [], "checked_at": datetime.now(timezone.utc), "reason": reason}

class CurrentHazardProvider(ABC):
    key = "current_hazards"

    @abstractmethod
    async def get_active_flood_events(self, bbox: list[float] | None = None) -> dict: ...

    @abstractmethod
    async def get_active_landslide_events(self, bbox: list[float] | None = None) -> dict: ...

class RoadClosureProvider(ABC):
    key = "road_closures"

    @abstractmethod
    async def get_road_closures(self, bbox: list[float] | None = None) -> dict: ...

class UnavailableCurrentHazardProvider(CurrentHazardProvider):
    async def get_active_flood_events(self, bbox=None) -> dict:
        return unavailable("flood_events", "No verified current flood-event feed is connected.")

    async def get_active_landslide_events(self, bbox=None) -> dict:
        return unavailable("landslide_events", "No verified current landslide-event feed is connected.")

class UnavailableRoadClosureProvider(RoadClosureProvider):
    async def get_road_closures(self, bbox=None) -> dict:
        return unavailable("road_closures", "No verified road-closure feed (PWD/disaster alerts) is connected; user reports are shown as unverified issues only.")

def current_hazard_provider() -> CurrentHazardProvider:
    return UnavailableCurrentHazardProvider()

def road_closure_provider() -> RoadClosureProvider:
    return UnavailableRoadClosureProvider()
