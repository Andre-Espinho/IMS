"""API tests: item listing, detail, edits, movements and import endpoints."""

import openpyxl
import pytest
from fastapi.testclient import TestClient

from ims.db import init_db, make_engine
from ims.main import create_app
from ims.models import Item, Location, Stock
from ims.db import session_factory


@pytest.fixture()
def client(tmp_path):
    engine = make_engine(tmp_path / "api.sqlite3")
    init_db(engine)
    with session_factory(engine)() as s:
        s.add_all([
            Item(id=1, description="Ficha HARTING teste", brand="HARTING", reference="R1"),
            Item(id=2, description="Disjuntor SCHNEIDER", brand="SCHNEIDER", reference="A9R41225"),
            Location(id=10, estante=5, prateleira="4"),
        ])
        s.add(Stock(item_id=1, location_id=10, qty=3))
        s.commit()
    with TestClient(create_app(engine)) as c:
        yield c
    engine.dispose()


def test_list_items_with_search_and_stock_filters(client):
    data = client.get("/api/items").json()
    assert data["total"] == 2
    item1 = next(i for i in data["items"] if i["id"] == 1)
    assert item1["stock_total"] == 3
    assert item1["locations"] == ["E5-P4 (3)"]

    assert client.get("/api/items", params={"q": "schneider"}).json()["total"] == 1
    assert client.get("/api/items", params={"stock": "zero"}).json()["total"] == 1
    assert client.get("/api/items", params={"stock": "in_stock"}).json()["total"] == 1
    assert client.get("/api/items", params={"estante": 5, "prateleira": "4"}).json()["total"] == 1


def test_sort_by_columns_and_direction(client):
    def ids(**params):
        return [i["id"] for i in client.get("/api/items", params=params).json()["items"]]

    assert ids(sort="description") == [2, 1]  # 'Disjuntor' before 'Ficha'
    assert ids(sort="description", order="desc") == [1, 2]
    assert ids(sort="id", order="desc") == [2, 1]
    assert ids(sort="stock", order="desc") == [1, 2]  # item 1 has stock 3, item 2 has none
    assert ids(sort="stock") == [2, 1]
    assert ids(sort="location") == [1, 2]  # item 2 has no location: nulls last
    assert ids(sort="location", order="desc") == [1, 2]  # nulls stay last in both directions
    assert ids(sort="brand") == [1, 2]  # HARTING before SCHNEIDER
    assert ids(sort="brand", order="desc") == [2, 1]
    assert ids(sort="verified") == [1, 2]  # both unverified: id breaks the tie


def test_sort_rejects_unknown_column(client):
    assert client.get("/api/items", params={"sort": "nope"}).status_code == 422


def test_item_detail_includes_stock_and_history(client):
    client.post("/api/movements", json={"type": "OUT", "item_id": 1, "qty": 1, "from_location_id": 10})
    detail = client.get("/api/items/1").json()
    assert detail["stock_total"] == 2
    assert detail["stock"] == [{"location_id": 10, "location": "E5-P4", "qty": 2}]
    assert detail["movements"][0]["type"] == "OUT"


def test_unknown_item_is_404(client):
    assert client.get("/api/items/999").status_code == 404


def test_patch_item_updates_fields_and_blanks_become_null(client):
    response = client.patch("/api/items/1", json={"brand": "  ", "notes": "frágil"})
    assert response.status_code == 200
    detail = client.get("/api/items/1").json()
    assert detail["brand"] is None
    assert detail["notes"] == "frágil"


def test_patch_rejects_empty_description_and_unknown_fields(client):
    assert client.patch("/api/items/1", json={"description": "  "}).status_code == 422
    assert client.patch("/api/items/1", json={"stock_total": 99}).status_code == 422


def test_movement_rule_violation_returns_422_with_portuguese_message(client):
    response = client.post("/api/movements", json={"type": "OUT", "item_id": 1, "qty": 50, "from_location_id": 10})
    assert response.status_code == 422
    assert "Stock insuficiente" in response.json()["detail"]


def test_create_movement_and_list_it(client):
    response = client.post("/api/movements", json={
        "type": "IN", "item_id": 2, "qty": 4, "to_location_id": 10, "operator": "Andre",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["changed"] is True
    assert body["movement"]["to_location"] == "E5-P4"
    assert body["movement"]["source"] == "local"

    listed = client.get("/api/movements", params={"item_id": 2}).json()
    assert len(listed) == 1 and listed[0]["operator"] == "Andre"


def test_no_op_adjust_reports_not_changed(client):
    response = client.post("/api/movements", json={"type": "ADJUST", "item_id": 1, "qty": 3, "to_location_id": 10})
    assert response.json() == {"changed": False}


def test_locations_endpoint_lists_labels(client):
    labels = [loc["label"] for loc in client.get("/api/locations").json()]
    assert "Sem localização" in labels and "E5-P4" in labels


def _workbook_bytes(tmp_path) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "INVENTARIO test"
    ws.append(["DESCRICAO", "MARCA", "REFERENCIA", "id", "QTD_STOCK", "PRATELEIRA", "ESTANTE"])
    ws.append(["Item novo", "HARTING", "N1", 500, 2, "3", 2])
    path = tmp_path / "in.xlsx"
    wb.save(path)
    return path.read_bytes()


def test_import_dry_run_then_commit(client, tmp_path):
    data = _workbook_bytes(tmp_path)
    files = {"file": ("inv.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    dry = client.post("/api/import/dry-run", files=files).json()
    assert dry["rows"] == 1 and dry["committed"] is False

    committed = client.post("/api/import/commit", files=files).json()
    assert committed["new_items"] == 1 and committed["committed"] is True
    assert client.get("/api/items/500").json()["stock_total"] == 2


def test_import_rejects_non_xlsx(client):
    response = client.post("/api/import/dry-run", files={"file": ("x.txt", b"hi", "text/plain")})
    assert response.status_code == 422
