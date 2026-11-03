"""Phase 2 acceptance: import the real workbook (local, git-ignored) and re-run safely."""

from pathlib import Path

import openpyxl
import pytest
from sqlalchemy import func, select

from ims.db import init_db, make_engine, session_factory
from ims.importer import analyse, commit
from ims.models import Item, Movement, Stock

WORKBOOK = Path(__file__).resolve().parents[2] / "Inventário.xlsx"
needs_workbook = pytest.mark.skipif(not WORKBOOK.exists(), reason="Inventário.xlsx not present")


def _make_small_workbook(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "INVENTARIO test"
    ws.append(["DESCRICAO", "MARCA", "REFERENCIA", "id", "QTD_STOCK", "PRATELEIRA", "ESTANTE", "QTD_ALOCADA", "S_N", "EAN"])
    ws.append(["Item A", "HARTING", "R1", 1, 5, "4", 5, 99, None, None])
    ws.append(["Item B", "-", "-", 2, 0, None, None, None, "SN-2", None])
    wb.save(path)
    return path


@pytest.fixture()
def session_maker(tmp_path):
    engine = make_engine(":memory:")
    init_db(engine)
    yield session_factory(engine)
    engine.dispose()


def test_small_import_ignores_allocation_and_seeds_locations(tmp_path, session_maker):
    wb = _make_small_workbook(tmp_path / "small.xlsx")
    with session_maker() as s:
        report = commit(s, wb)
    assert report.new_items == 2
    assert report.committed

    with session_maker() as s:
        a = s.get(Item, 1)
        assert a.brand == "HARTING" and a.reference == "R1"
        assert s.scalar(select(Stock.qty).where(Stock.item_id == 1)) == 5
        b = s.get(Item, 2)
        assert b.brand is None and b.reference is None  # '-' placeholders are not kept
        assert b.serial_number == "SN-2"
        movements = s.scalars(select(Movement)).all()
        assert {m.type for m in movements} == {"IMPORT"}
        assert all(m.source == "import" for m in movements)


def test_rerun_only_records_stock_difference(tmp_path, session_maker):
    wb = _make_small_workbook(tmp_path / "small.xlsx")
    with session_maker() as s:
        commit(s, wb)
    # Change qty of item 1 from 5 to 3 and re-import.
    book = openpyxl.load_workbook(wb)
    book.active["E2"] = 3
    book.save(wb)
    with session_maker() as s:
        report = commit(s, wb)
    assert report.new_items == 0 and report.updated_items == 2
    with session_maker() as s:
        assert s.scalar(select(Stock.qty).where(Stock.item_id == 1)) == 3
        adjust = s.scalars(select(Movement).where(Movement.type == "ADJUST")).all()
        assert len(adjust) == 1 and adjust[0].qty == -2


@needs_workbook
def test_real_workbook_dry_run_reports_items_and_issues(session_maker):
    report = analyse(WORKBOOK)
    assert report.rows == 828
    assert any("REFERENCIA repetida" in issue for issue in report.issues)
    assert any("sem localização" in issue for issue in report.issues)
    assert not any("id " in issue and "repetido" in issue for issue in report.issues)


@needs_workbook
def test_real_workbook_commit_imports_828_items(session_maker):
    with session_maker() as s:
        report = commit(s, WORKBOOK)
    assert report.new_items == 828
    with session_maker() as s:
        assert s.scalar(select(func.count()).select_from(Item)) == 828
        # Items sharing a reference must both be kept (reference is not unique).
        dup = s.scalars(select(Item).where(Item.reference == "27230171")).all()
        assert len(dup) == 2
