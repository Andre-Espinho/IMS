"""Excel export: layout, one row per stocked location, inactive items left out."""

import io
from datetime import datetime, timezone

import openpyxl
import pytest
from fastapi.testclient import TestClient

from ims.db import init_db, make_engine, session_factory
from ims.main import create_app
from ims.models import Item, Location, Stock


@pytest.fixture()
def client(tmp_path):
    engine = make_engine(tmp_path / "export.sqlite3")
    init_db(engine)
    with session_factory(engine)() as s:
        s.add_all([
            Item(id=1, description="Ficha HARTING", brand="HARTING", reference="R1", ean="123",
                 verified_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)),
            Item(id=2, description="Sem stock"),
            Item(id=3, description="Desativado", active=False),
            Location(id=10, estante=5, prateleira="4"),
            Location(id=11, estante=3, prateleira="Topo"),
        ])
        s.add_all([
            Stock(item_id=1, location_id=10, qty=3),
            Stock(item_id=1, location_id=11, qty=2),
        ])
        s.commit()
    with TestClient(create_app(engine)) as c:
        yield c
    engine.dispose()


def _rows(response):
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    return ws.title, [list(row) for row in ws.iter_rows(values_only=True)]


def test_export_returns_a_downloadable_xlsx(client):
    response = client.get("/api/export/xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert response.headers["content-disposition"].startswith('attachment; filename="Inventario-')


def test_export_uses_the_imported_layout_and_one_row_per_location(client):
    title, rows = _rows(client.get("/api/export/xlsx"))
    assert title.startswith("INVENTARIO ")
    assert rows[0] == ["DESCRICAO", "MARCA", "REFERENCIA", "id", "QTD_STOCK",
                       "PRATELEIRA", "ESTANTE", "S_N", "EAN", "Verificado"]
    data = rows[1:]
    # item 1 has two stocked locations -> two rows, sorted by rack then shelf
    assert data[0][:7] == ["Ficha HARTING", "HARTING", "R1", 1, 2, "Topo", 3]
    assert data[1][:7] == ["Ficha HARTING", "HARTING", "R1", 1, 3, "4", 5]
    assert data[0][8] == "123" and data[0][9] == data[1][9]
    assert len(data) == 3


def test_items_without_stock_get_a_zero_row_and_inactive_items_are_left_out(client):
    _, rows = _rows(client.get("/api/export/xlsx"))
    no_stock = [r for r in rows[1:] if r[3] == 2]
    assert no_stock == [["Sem stock", None, None, 2, 0, None, None, None, None, None]]
    assert all(r[3] != 3 for r in rows[1:])


def test_verified_date_is_written_as_local_day(client):
    _, rows = _rows(client.get("/api/export/xlsx"))
    verified = rows[1][9]
    assert verified in ("2026-10-01", "2026-10-02")  # depends on the PC's time zone
