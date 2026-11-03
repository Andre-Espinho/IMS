"""Import an inventory workbook (legacy layout) into the database. See docs/SPEC.md §7.

Columns are matched by header name, never by position, because the legacy
sheets change column order between snapshots. `QTD_ALOCADA` is ignored
(allocation was removed from the model).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import UNASSIGNED_LOCATION_ID, Item, Location, Movement, Stock

REQUIRED = ["DESCRICAO", "id", "QTD_STOCK"]
OPTIONAL = ["MARCA", "REFERENCIA", "PRATELEIRA", "ESTANTE", "S_N", "EAN", "Verificado"]


@dataclass
class ImportReport:
    sheet: str
    rows: int = 0
    new_items: int = 0
    updated_items: int = 0
    adjusted_stock: int = 0
    issues: list[str] = field(default_factory=list)
    committed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "sheet": self.sheet,
            "rows": self.rows,
            "new_items": self.new_items,
            "updated_items": self.updated_items,
            "adjusted_stock": self.adjusted_stock,
            "issues": self.issues,
            "committed": self.committed,
        }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _placeholder_to_none(value: Any) -> str | None:
    """The workbook uses '-' for 'unknown'."""
    text = _clean(value)
    return None if text in (None, "-") else text


def _int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_rows(path: Path, sheet: str | None) -> tuple[str, list[dict[str, Any]], list[str]]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[sheet] if sheet else wb.worksheets[-1]
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        headers = [str(h).strip() if h is not None else "" for h in header_row]
        missing = [name for name in REQUIRED if name not in headers]
        if missing:
            raise ValueError(f"Colunas obrigatórias em falta na folha '{ws.title}': {missing}")
        rows = []
        for raw in ws.iter_rows(min_row=2, values_only=True):
            if not any(v is not None and str(v).strip() != "" for v in raw):
                continue
            rows.append({h: raw[i] for i, h in enumerate(headers) if h})
        return ws.title, rows, headers
    finally:
        wb.close()


def _location_key(row: dict[str, Any]) -> tuple[int | None, str | None]:
    return _int_or_none(row.get("ESTANTE")), _clean(row.get("PRATELEIRA"))


def analyse(path: Path, sheet: str | None = None) -> ImportReport:
    """Dry run: read and check the workbook without touching the database."""
    sheet_name, rows, _ = _read_rows(path, sheet)
    report = ImportReport(sheet=sheet_name, rows=len(rows))

    ids = Counter(_int_or_none(r.get("id")) for r in rows)
    for item_id, n in ids.items():
        if item_id is None:
            report.issues.append("Linha sem id válido")
        elif n > 1:
            report.issues.append(f"id {item_id} repetido {n} vezes")

    refs = Counter(_clean(r.get("REFERENCIA")) for r in rows)
    dup_refs = [ref for ref, n in refs.items() if ref and ref != "-" and n > 1]
    for ref in dup_refs:
        report.issues.append(f"REFERENCIA repetida: {ref}")

    no_location = sum(1 for r in rows if _location_key(r) == (None, None))
    if no_location:
        report.issues.append(f"{no_location} itens sem localização (ficam em 'Sem localização')")

    unparsed_qty = [r.get("id") for r in rows if _int_or_none(r.get("QTD_STOCK")) is None]
    if unparsed_qty:
        report.issues.append(f"QTD_STOCK inválida em {len(unparsed_qty)} linhas (ids: {unparsed_qty[:10]})")

    negative = [r.get("id") for r in rows if (_int_or_none(r.get("QTD_STOCK")) or 0) < 0]
    if negative:
        report.issues.append(f"QTD_STOCK negativa em {len(negative)} linhas")

    return report


def commit(session: Session, path: Path, sheet: str | None = None) -> ImportReport:
    """Apply the workbook to the database. Re-running is safe: it updates
    attributes and records only the stock difference as ADJUST movements."""
    report = analyse(path, sheet)
    _, rows, _ = _read_rows(path, sheet)

    loc_cache: dict[tuple[int | None, str | None], int] = {}
    existing_locs = session.scalars(select(Location)).all()
    for loc in existing_locs:
        loc_cache[(loc.estante, loc.prateleira)] = loc.id
    next_loc_id = max([UNASSIGNED_LOCATION_ID, *loc_cache.values()]) + 1

    now = datetime.now(timezone.utc)
    for row in rows:
        item_id = _int_or_none(row.get("id"))
        qty = max(_int_or_none(row.get("QTD_STOCK")) or 0, 0)
        if item_id is None:
            continue

        key = _location_key(row)
        if key == (None, None):
            location_id = UNASSIGNED_LOCATION_ID
        elif key in loc_cache:
            location_id = loc_cache[key]
        else:
            location_id = next_loc_id
            session.add(Location(id=location_id, estante=key[0], prateleira=key[1]))
            loc_cache[key] = location_id
            next_loc_id += 1

        item = session.get(Item, item_id)
        verified = _clean(row.get("Verificado")) is not None
        if item is None:
            item = Item(id=item_id, description=_clean(row.get("DESCRICAO")) or "(sem descrição)")
            session.add(item)
            report.new_items += 1
            movement_type = "IMPORT"
            previous = 0
        else:
            report.updated_items += 1
            movement_type = "ADJUST"
            previous = session.scalar(
                select(Stock.qty).where(Stock.item_id == item_id, Stock.location_id == location_id)
            ) or 0

        item.description = _clean(row.get("DESCRICAO")) or item.description
        item.brand = _placeholder_to_none(row.get("MARCA"))
        item.reference = _placeholder_to_none(row.get("REFERENCIA"))
        item.ean = _clean(row.get("EAN"))
        item.serial_number = _clean(row.get("S_N"))
        if verified and item.verified_at is None:
            item.verified_at = now
        item.active = True

        stock = session.get(Stock, (item_id, location_id))
        if stock is None:
            stock = Stock(item_id=item_id, location_id=location_id, qty=0)
            session.add(stock)
        stock.qty = qty

        delta = qty - previous
        if movement_type == "IMPORT" or delta != 0:
            session.add(
                Movement(
                    type=movement_type,
                    item_id=item_id,
                    to_location_id=location_id,
                    qty=delta if movement_type == "ADJUST" else qty,
                    reason="Importação da folha de inventário",
                    source="import",
                    created_at=now,
                )
            )
            if movement_type == "ADJUST":
                report.adjusted_stock += 1

    session.commit()
    report.committed = True
    return report
