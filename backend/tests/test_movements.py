"""Phase 3 acceptance: every movement rule in docs/SPEC.md §5 has a test."""

import pytest
from sqlalchemy import select

from ims.db import init_db, make_engine, session_factory
from ims.models import UNASSIGNED_LOCATION_ID, Item, Location, Movement, Stock
from ims.services import MovementError, apply_movement, find_or_create_location, parse_label


@pytest.fixture()
def session(tmp_path):
    engine = make_engine(tmp_path / "t.sqlite3")
    init_db(engine)
    with session_factory(engine)() as s:
        s.add(Item(id=1, description="Ficha teste"))
        s.add(Location(id=10, estante=5, prateleira="4"))
        s.add(Location(id=11, estante=3, prateleira="Topo"))
        s.commit()
        yield s
    engine.dispose()


def qty_at(session, location_id, item_id=1):
    stock = session.get(Stock, (item_id, location_id))
    return stock.qty if stock else 0


def test_parse_label_formats():
    assert parse_label("E5-P4") == (5, "4")
    assert parse_label("e3-topo") == (3, "Topo")
    with pytest.raises(MovementError):
        parse_label("P4")


def test_in_defaults_to_unassigned_location(session):
    apply_movement(session, type="IN", item_id=1, qty=4)
    assert qty_at(session, UNASSIGNED_LOCATION_ID) == 4


def test_in_requires_positive_qty(session):
    with pytest.raises(MovementError):
        apply_movement(session, type="IN", item_id=1, qty=0)
    with pytest.raises(MovementError):
        apply_movement(session, type="IN", item_id=1, qty=None)


def test_out_rejects_insufficient_stock_and_leaves_no_trace(session):
    apply_movement(session, type="IN", item_id=1, qty=2, to_location_id=10)
    with pytest.raises(MovementError, match="Stock insuficiente"):
        apply_movement(session, type="OUT", item_id=1, qty=3, from_location_id=10)
    assert qty_at(session, 10) == 2
    assert session.scalars(select(Movement).where(Movement.type == "OUT")).all() == []


def test_out_uses_only_stocked_location_when_unspecified(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    apply_movement(session, type="OUT", item_id=1, qty=2)
    assert qty_at(session, 10) == 3


def test_out_is_ambiguous_when_stock_is_in_two_places(session):
    apply_movement(session, type="IN", item_id=1, qty=1, to_location_id=10)
    apply_movement(session, type="IN", item_id=1, qty=1, to_location_id=11)
    with pytest.raises(MovementError, match="localização de origem"):
        apply_movement(session, type="OUT", item_id=1, qty=1)


def test_move_transfers_stock(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    apply_movement(session, type="MOVE", item_id=1, qty=2, from_location_id=10, to_location_id=11)
    assert qty_at(session, 10) == 3
    assert qty_at(session, 11) == 2
    move = session.scalars(select(Movement).where(Movement.type == "MOVE")).one()
    assert move.from_location_id == 10 and move.to_location_id == 11 and move.qty == 2


def test_move_rejects_same_location_and_missing_ends(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    with pytest.raises(MovementError, match="iguais"):
        apply_movement(session, type="MOVE", item_id=1, qty=1, from_location_id=10, to_location_id=10)
    with pytest.raises(MovementError, match="origem e o destino"):
        apply_movement(session, type="MOVE", item_id=1, qty=1, from_location_id=10)


def test_adjust_sets_counted_quantity_and_records_delta(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    movement = apply_movement(session, type="ADJUST", item_id=1, qty=3, to_location_id=10)
    assert qty_at(session, 10) == 3
    assert movement.qty == -2


def test_adjust_with_no_difference_records_nothing(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    assert apply_movement(session, type="ADJUST", item_id=1, qty=5, to_location_id=10) is None
    assert len(session.scalars(select(Movement).where(Movement.type == "ADJUST")).all()) == 0


def test_adjust_rejects_negative_count(session):
    with pytest.raises(MovementError):
        apply_movement(session, type="ADJUST", item_id=1, qty=-1, to_location_id=10)


def test_verify_sets_timestamp_without_changing_stock(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    movement = apply_movement(session, type="VERIFY", item_id=1)
    assert movement.qty == 0
    assert session.get(Item, 1).verified_at is not None
    assert qty_at(session, 10) == 5


def test_unknown_item_and_bad_type_are_rejected(session):
    with pytest.raises(MovementError, match="não existe"):
        apply_movement(session, type="IN", item_id=999, qty=1)
    with pytest.raises(MovementError, match="Tipo"):
        apply_movement(session, type="DELETE", item_id=1)


def test_movements_are_append_only_history(session):
    apply_movement(session, type="IN", item_id=1, qty=5, to_location_id=10)
    apply_movement(session, type="OUT", item_id=1, qty=1, from_location_id=10)
    assert len(session.scalars(select(Movement)).all()) == 2


def test_find_or_create_location_reuses_existing_slot(session):
    existing = find_or_create_location(session, 5, "4")
    assert existing.id == 10
    created = find_or_create_location(session, 7, "2")
    assert created.id not in (0, 10, 11)
    assert created.label == "E7-P2"
