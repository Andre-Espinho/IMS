"""Phase 1 acceptance: schema creates, constraints hold, health endpoint works."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ims.db import init_db, make_engine, session_factory
from ims.main import create_app
from ims.models import (
    UNASSIGNED_LOCATION_ID,
    Item,
    Location,
    Movement,
    Stock,
)


@pytest.fixture()
def engine():
    eng = make_engine(":memory:")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with session_factory(engine)() as s:
        yield s


def test_init_db_is_idempotent_and_seeds_unassigned_location(engine):
    init_db(engine)  # second call must not fail
    with session_factory(engine)() as s:
        loc = s.get(Location, UNASSIGNED_LOCATION_ID)
        assert loc is not None
        assert loc.label == "Sem localização"


def test_location_label_formats_shelf_and_top(session):
    session.add_all([
        Location(id=10, estante=5, prateleira="4"),
        Location(id=11, estante=3, prateleira="Topo"),
    ])
    session.commit()
    assert session.get(Location, 10).label == "E5-P4"
    assert session.get(Location, 11).label == "E3-Topo"


def test_location_slot_is_unique(session):
    session.add(Location(id=20, estante=2, prateleira="3"))
    session.commit()
    session.add(Location(id=21, estante=2, prateleira="3"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_stock_cannot_go_negative(session):
    session.add(Item(id=349, description="Teste"))
    session.commit()
    session.add(Stock(item_id=349, location_id=UNASSIGNED_LOCATION_ID, qty=-1))
    with pytest.raises(IntegrityError):
        session.commit()


def test_movement_type_and_source_are_checked(session):
    session.add(Item(id=350, description="Teste"))
    session.commit()
    session.add(Movement(type="BOGUS", item_id=350, qty=1, source="local"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(Movement(type="IN", item_id=350, qty=1, source="nowhere"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_external_ref_is_unique_for_idempotent_mobile_movements(session):
    session.add(Item(id=351, description="Teste"))
    session.commit()
    session.add(Movement(type="IN", item_id=351, qty=1, source="mobile", external_ref="sp-1"))
    session.commit()
    session.add(Movement(type="IN", item_id=351, qty=1, source="mobile", external_ref="sp-1"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_health_endpoint(engine):
    app = create_app(engine)
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
