"""CRUD rules: item create/edit/deactivate, location create/edit/delete, movement void."""

import pytest
from fastapi.testclient import TestClient

from ims.db import init_db, make_engine, session_factory
from ims.main import create_app
from ims.models import Item, Location, Stock


@pytest.fixture()
def client(tmp_path):
    engine = make_engine(tmp_path / "crud.sqlite3")
    init_db(engine)
    with session_factory(engine)() as s:
        s.add_all([Item(id=1, description="Ficha teste"), Location(id=10, estante=5, prateleira="4")])
        s.commit()
    with TestClient(create_app(engine)) as c:
        yield c
    engine.dispose()


# ---------- items ----------

def test_create_item_with_auto_id_and_initial_stock(client):
    response = client.post("/api/items", json={
        "description": "Novo", "brand": " ACME ", "initial_qty": 4, "initial_location_id": 10,
    })
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert new_id == 2  # next free id after 1
    detail = client.get(f"/api/items/{new_id}").json()
    assert detail["brand"] == "ACME"
    assert detail["stock_total"] == 4
    assert detail["movements"][0]["type"] == "IN"


def test_create_item_rejects_blank_description_and_duplicate_id(client):
    assert client.post("/api/items", json={"description": "   "}).status_code == 422
    assert client.post("/api/items", json={"id": 1, "description": "Outro"}).status_code == 409


def test_update_item_fields(client):
    response = client.patch("/api/items/1", json={"reference": "R-9", "ean": ""})
    assert response.status_code == 200
    detail = client.get("/api/items/1").json()
    assert detail["reference"] == "R-9"
    assert detail["ean"] is None


def test_delete_is_soft_and_requires_zero_stock(client):
    client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 2, "to_location_id": 10})
    refused = client.delete("/api/items/1")
    assert refused.status_code == 422
    client.post("/api/movements", json={"type": "OUT", "item_id": 1, "qty": 2, "from_location_id": 10})
    assert client.delete("/api/items/1").json() == {"id": 1, "active": False}
    # hidden from the default list, still readable, history kept
    assert client.get("/api/items").json()["total"] == 0
    assert client.get("/api/items", params={"status": "inactive"}).json()["total"] == 1
    detail = client.get("/api/items/1").json()
    assert detail["active"] is False and len(detail["movements"]) == 2


def test_inactive_item_cannot_receive_stock_and_can_be_reactivated(client):
    client.delete("/api/items/1")
    assert client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 1}).status_code == 422
    assert client.patch("/api/items/1", json={"active": True}).status_code == 200
    assert client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 1}).status_code == 201


def test_unverify_clears_verification_and_keeps_history(client):
    client.post("/api/movements", json={"type": "VERIFY", "item_id": 1})
    assert client.get("/api/items/1").json()["verified_at"] is not None
    assert client.patch("/api/items/1", json={"verified": False}).status_code == 200
    detail = client.get("/api/items/1").json()
    assert detail["verified_at"] is None
    assert [m["type"] for m in detail["movements"]] == ["VERIFY"]  # the earlier verification stays in the log


def test_verify_flag_via_patch_sets_then_keeps_timestamp(client):
    client.patch("/api/items/1", json={"verified": True})
    first = client.get("/api/items/1").json()["verified_at"]
    assert first is not None
    client.patch("/api/items/1", json={"verified": True})
    assert client.get("/api/items/1").json()["verified_at"] == first


def test_unknown_item_is_404_for_update_and_delete(client):
    assert client.patch("/api/items/999", json={"notes": "x"}).status_code == 404
    assert client.delete("/api/items/999").status_code == 404


# ---------- locations ----------

def test_create_location_and_reject_duplicate(client):
    created = client.post("/api/locations", json={"estante": 3, "prateleira": "Topo"})
    assert created.status_code == 201
    assert created.json()["label"] == "E3-Topo"
    assert client.post("/api/locations", json={"estante": 5, "prateleira": "4"}).status_code == 409


def test_rack_without_shelf_is_labelled_without_suffix(client):
    client.post("/api/locations", json={"estante": 2, "prateleira": None})
    labels = [loc["label"] for loc in client.get("/api/locations").json()]
    assert "E2" in labels
    assert "E2-PNone" not in labels


def test_edit_can_set_a_shelf_on_a_rack_only_location(client):
    created = client.post("/api/locations", json={"estante": 2, "prateleira": ""}).json()
    assert created["prateleira"] is None
    response = client.patch(f"/api/locations/{created['id']}", json={"estante": 2, "prateleira": "3"})
    assert response.status_code == 200
    assert response.json()["label"] == "E2-P3"


def test_edit_can_clear_a_shelf(client):
    response = client.patch("/api/locations/10", json={"estante": 5, "prateleira": "  "})
    assert response.status_code == 200
    assert response.json()["label"] == "E5"


def test_only_one_rack_only_location_per_rack(client):
    client.post("/api/locations", json={"estante": 2, "prateleira": None})
    assert client.post("/api/locations", json={"estante": 2, "prateleira": ""}).status_code == 409


def test_location_name_becomes_the_label_and_blank_falls_back(client):
    created = client.post("/api/locations", json={"estante": 4, "prateleira": "1", "name": "Corredor A"}).json()
    assert created["label"] == "Corredor A" and created["name"] == "Corredor A"

    renamed = client.patch(f"/api/locations/{created['id']}", json={"estante": 4, "prateleira": "1", "name": "  "})
    assert renamed.json()["name"] is None
    assert renamed.json()["label"] == "E4-P1"


def test_name_survives_rack_and_shelf_changes_and_shows_in_items(client):
    client.patch("/api/locations/10", json={"estante": 5, "prateleira": "4", "name": "Gaveta grande"})
    client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 2, "to_location_id": 10})
    client.patch("/api/locations/10", json={"estante": 6, "prateleira": "2", "name": "Gaveta grande"})
    item = client.get("/api/items/1").json()
    assert item["stock"][0]["location"] == "Gaveta grande"
    assert client.get("/api/items").json()["items"][0]["locations"] == ["Gaveta grande (2)"]


def test_location_name_migration_adds_column_to_old_database(tmp_path):
    import sqlite3

    from ims.db import init_db, make_engine, session_factory

    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE location (id INTEGER PRIMARY KEY, estante INTEGER, prateleira VARCHAR(20),"
        " CONSTRAINT uq_location_slot UNIQUE (estante, prateleira))"
    )
    conn.execute("INSERT INTO location (id, estante, prateleira) VALUES (10, 5, '4')")
    conn.commit()
    conn.close()

    engine = make_engine(db)
    init_db(engine)
    with session_factory(engine)() as s:
        loc = s.get(Location, 10)
        assert loc.name is None and loc.label == "E5-P4"
    engine.dispose()


def test_update_location_label(client):
    response = client.patch("/api/locations/10", json={"estante": 6, "prateleira": "2"})
    assert response.status_code == 200
    assert response.json()["label"] == "E6-P2"


def test_unassigned_location_is_protected(client):
    assert client.patch("/api/locations/0", json={"estante": 1, "prateleira": "1"}).status_code == 422
    assert client.delete("/api/locations/0").status_code == 422


def test_delete_location_refused_when_it_has_stock_or_history(client):
    client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 2, "to_location_id": 10})
    assert client.delete("/api/locations/10").status_code == 422  # has stock
    client.post("/api/movements", json={"type": "OUT", "item_id": 1, "qty": 2, "from_location_id": 10})
    assert client.delete("/api/locations/10").status_code == 422  # has history


def test_delete_empty_unused_location(client):
    new = client.post("/api/locations", json={"estante": 9, "prateleira": "3"}).json()
    assert client.delete(f"/api/locations/{new['id']}").json() == {"id": new["id"], "deleted": True}
    assert new["label"] not in [loc["label"] for loc in client.get("/api/locations").json()]


# ---------- clear local data ----------

def test_clear_data_requires_typed_confirmation(client):
    client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 2, "to_location_id": 10})
    assert client.post("/api/admin/clear-data", json={"confirm": ""}).status_code == 422
    assert client.post("/api/admin/clear-data", json={"confirm": "sim"}).status_code == 422
    assert client.get("/api/items/1").json()["stock_total"] == 2  # nothing was deleted


def test_clear_data_removes_inventory_but_keeps_unassigned_location(client):
    client.post("/api/movements", json={"type": "IN", "item_id": 1, "qty": 2, "to_location_id": 10})
    response = client.post("/api/admin/clear-data", json={"confirm": "APAGAR"})
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"]["items"] == 1 and body["deleted"]["movements"] == 1
    assert client.get("/api/items", params={"status": "all"}).json()["total"] == 0
    assert client.get("/api/movements").json() == []
    labels = [loc["label"] for loc in client.get("/api/locations").json()]
    assert labels == ["Sem localização"]


def test_clear_data_accepts_english_word(client):
    assert client.post("/api/admin/clear-data", json={"confirm": "delete"}).status_code == 200


# ---------- void ----------

def _movement(client, **body):
    return client.post("/api/movements", json=body).json()["movement"]


def test_void_in_reverses_stock_and_keeps_original(client):
    m = _movement(client, type="IN", item_id=1, qty=5, to_location_id=10)
    response = client.post(f"/api/movements/{m['id']}/void", json={"operator": "Ana"})
    assert response.status_code == 201
    assert client.get("/api/items/1").json()["stock_total"] == 0
    history = client.get("/api/movements", params={"item_id": 1}).json()
    assert len(history) == 2
    assert {h["type"] for h in history} == {"IN", "OUT"}


def test_void_twice_is_refused(client):
    m = _movement(client, type="IN", item_id=1, qty=5, to_location_id=10)
    client.post(f"/api/movements/{m['id']}/void")
    response = client.post(f"/api/movements/{m['id']}/void")
    assert response.status_code == 422
    assert "já foi anulado" in response.json()["detail"]


def test_void_out_and_move(client):
    _movement(client, type="IN", item_id=1, qty=5, to_location_id=10)
    out = _movement(client, type="OUT", item_id=1, qty=2, from_location_id=10)
    client.post(f"/api/movements/{out['id']}/void")
    assert client.get("/api/items/1").json()["stock_total"] == 5

    mv = _movement(client, type="MOVE", item_id=1, qty=3, from_location_id=10, to_location_id=0)
    client.post(f"/api/movements/{mv['id']}/void")
    assert client.get("/api/items/1").json()["stock_total"] == 5
    assert client.get("/api/items/1").json()["stock"] == [{"location_id": 10, "location": "E5-P4", "qty": 5}]


def test_void_adjust_restores_previous_count(client):
    _movement(client, type="IN", item_id=1, qty=5, to_location_id=10)
    adj = _movement(client, type="ADJUST", item_id=1, qty=2, to_location_id=10)
    client.post(f"/api/movements/{adj['id']}/void")
    assert client.get("/api/items/1").json()["stock_total"] == 5


def test_void_refuses_verify_and_import_and_unknown(client):
    verify = _movement(client, type="VERIFY", item_id=1)
    assert client.post(f"/api/movements/{verify['id']}/void").status_code == 422
    assert client.post("/api/movements/nope/void").status_code == 422


def test_voidable_flag_reflects_state(client):
    m = _movement(client, type="IN", item_id=1, qty=5, to_location_id=10)
    before = client.get("/api/items/1").json()["movements"][0]
    assert before["voidable"] is True
    client.post(f"/api/movements/{m['id']}/void")
    after = {x["id"]: x for x in client.get("/api/items/1").json()["movements"]}
    assert after[m["id"]]["voidable"] is False
