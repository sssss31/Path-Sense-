import pytest
from types import SimpleNamespace
from app.core.domain import DELIVERY_TRANSITIONS, SENSITIVE_DELIVERY_STATUSES
from app.schemas.delivery import DeliveryCreate, DeliveryUpdate
from app.services.delivery import DeliveryService, allowed_transitions

class Session:
    async def commit(self): pass

def row(status="planned"):
    return SimpleNamespace(status=status, planned_departure=None, actual_arrival=None, notes=None, status_history=[], analysis_id=None, eta=None)

@pytest.mark.asyncio
async def test_completed_delivery_cannot_return_to_planned():
    with pytest.raises(ValueError):
        await DeliveryService().update(Session(), row("completed"), DeliveryUpdate(status="planned"))

@pytest.mark.asyncio
async def test_planned_delivery_can_start_transit_and_records_history():
    r = row("planned")
    await DeliveryService().update(Session(), r, DeliveryUpdate(status="in_transit", status_note="Driver departed"))
    assert r.status == "in_transit"
    assert r.status_history[-1]["from_status"] == "planned" and r.status_history[-1]["to_status"] == "in_transit" and r.status_history[-1]["note"] == "Driver departed"

@pytest.mark.asyncio
async def test_planned_cannot_jump_to_delayed_or_completed():
    for target in ["delayed", "completed"]:
        with pytest.raises(ValueError):
            await DeliveryService().update(Session(), row("planned"), DeliveryUpdate(status=target))

@pytest.mark.asyncio
async def test_completion_sets_actual_arrival():
    r = row("in_transit")
    await DeliveryService().update(Session(), r, DeliveryUpdate(status="completed"))
    assert r.status == "completed" and r.actual_arrival is not None

def test_transition_table_matches_domain_rules():
    assert allowed_transitions("planned") == ["in_transit", "cancelled"]
    assert allowed_transitions("in_transit") == ["delayed", "completed", "cancelled"]
    assert allowed_transitions("delayed") == ["in_transit", "completed", "cancelled"]
    assert allowed_transitions("completed") == [] and allowed_transitions("cancelled") == []
    assert set(SENSITIVE_DELIVERY_STATUSES) == {"completed", "cancelled"}
    for status, targets in DELIVERY_TRANSITIONS.items():
        assert status not in targets

def test_delivery_create_rejects_unknown_priority():
    with pytest.raises(ValueError):
        DeliveryCreate(analysis_id="00000000-0000-0000-0000-000000000000", priority="urgent-ish")
    assert DeliveryCreate(analysis_id="00000000-0000-0000-0000-000000000000", priority="critical", vehicle="4x4 Utility Vehicle").vehicle == "4x4 Utility Vehicle"
