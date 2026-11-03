"""HTTP API used by the Electron UI. See docs/SPEC.md §8."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.orm import Session

from . import importer
from .models import UNASSIGNED_LOCATION_ID, Item, Location, Movement, Stock, SyncRun, utcnow
from .services import MovementError, apply_movement, item_total, void_movement
from .sharepoint import SharePointError

router = APIRouter(prefix="/api")


def get_session(request: Request):
    with request.app.state.session_factory() as session:
        yield session


# ---------- schemas ----------

class MovementIn(BaseModel):
    type: Literal["IN", "OUT", "MOVE", "ADJUST", "VERIFY"]
    item_id: int
    qty: int | None = None
    from_location_id: int | None = None
    to_location_id: int | None = None
    reason: str | None = None
    operator: str | None = None


class VoidIn(BaseModel):
    operator: str | None = None


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None  # blank = next free id
    description: str
    brand: str | None = None
    reference: str | None = None
    ean: str | None = None
    serial_number: str | None = None
    notes: str | None = None
    initial_qty: int | None = Field(default=None, ge=0)
    initial_location_id: int | None = None


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    brand: str | None = None
    reference: str | None = None
    ean: str | None = None
    serial_number: str | None = None
    notes: str | None = None
    active: bool | None = None
    verified: bool | None = None  # true = mark verified now; false = clear the verification


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estante: int = Field(ge=1)
    prateleira: str | None = None  # blank = rack without a shelf
    name: str | None = None  # blank = label comes from rack and shelf


# ---------- helpers ----------

def _iso(value):
    return value.isoformat() if value else None


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _location_dict(loc: Location) -> dict:
    return {
        "id": loc.id,
        "label": loc.label,
        "name": loc.name,
        "estante": loc.estante,
        "prateleira": loc.prateleira,
    }


REVERSIBLE_TYPES = ("IN", "OUT", "MOVE", "ADJUST")


def _voided_ids(session: Session) -> set[str]:
    """Ids of movements that already have a reversal ('void:<id>' marker)."""
    refs = session.scalars(select(Movement.external_ref).where(Movement.external_ref.like("void:%"))).all()
    return {ref[len("void:"):] for ref in refs if ref}


def _movement_dict(m: Movement, labels: dict[int, str], voided: set[str]) -> dict:
    return {
        "id": m.id,
        "created_at": _iso(m.created_at),
        "type": m.type,
        "item_id": m.item_id,
        "from_location": labels.get(m.from_location_id),
        "to_location": labels.get(m.to_location_id),
        "qty": m.qty,
        "reason": m.reason,
        "operator": m.operator,
        "source": m.source,
        "voidable": m.type in REVERSIBLE_TYPES and m.id not in voided,
    }


def _location_labels(session: Session) -> dict[int, str]:
    return {loc.id: loc.label for loc in session.scalars(select(Location)).all()}


def _item_or_404(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return item


# ---------- locations ----------

@router.get("/locations")
def list_locations(session: Session = Depends(get_session)):
    locations = session.scalars(select(Location).order_by(Location.estante, Location.prateleira)).all()
    return [_location_dict(loc) for loc in locations]


def _clean_shelf(value: str | None) -> str | None:
    return (value or "").strip() or None


def _check_unique_slot(session: Session, estante: int, prateleira: str | None, exclude_id: int | None = None) -> None:
    shelf_match = Location.prateleira.is_(None) if prateleira is None else Location.prateleira == prateleira
    stmt = select(Location.id).where(Location.estante == estante, shelf_match)
    if exclude_id is not None:
        stmt = stmt.where(Location.id != exclude_id)
    if session.scalar(stmt) is not None:
        raise HTTPException(status_code=409, detail="Já existe esta localização")


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, session: Session = Depends(get_session)):
    prateleira = _clean_shelf(body.prateleira)
    _check_unique_slot(session, body.estante, prateleira)
    next_id = (session.scalar(select(func.max(Location.id))) or 0) + 1
    loc = Location(id=next_id, estante=body.estante, prateleira=prateleira, name=_blank(body.name))
    session.add(loc)
    session.commit()
    return _location_dict(loc)


@router.patch("/locations/{location_id}")
def update_location(location_id: int, body: LocationIn, session: Session = Depends(get_session)):
    if location_id == UNASSIGNED_LOCATION_ID:
        raise HTTPException(status_code=422, detail="A localização 'Sem localização' não pode ser alterada")
    loc = session.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Localização não encontrada")
    prateleira = _clean_shelf(body.prateleira)
    _check_unique_slot(session, body.estante, prateleira, exclude_id=location_id)
    loc.estante = body.estante
    loc.prateleira = prateleira
    loc.name = _blank(body.name)
    session.commit()
    return _location_dict(loc)


@router.delete("/locations/{location_id}")
def delete_location(location_id: int, session: Session = Depends(get_session)):
    if location_id == UNASSIGNED_LOCATION_ID:
        raise HTTPException(status_code=422, detail="A localização 'Sem localização' não pode ser eliminada")
    loc = session.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Localização não encontrada")
    if session.scalar(select(Stock.item_id).where(Stock.location_id == location_id, Stock.qty > 0)) is not None:
        raise HTTPException(status_code=422, detail="A localização tem stock. Mova ou ajuste o stock primeiro")
    used = session.scalar(
        select(Movement.id).where(
            or_(Movement.from_location_id == location_id, Movement.to_location_id == location_id)
        )
    )
    if used is not None:
        raise HTTPException(status_code=422, detail="A localização tem movimentos registados e não pode ser eliminada")
    session.execute(Stock.__table__.delete().where(Stock.location_id == location_id))
    session.delete(loc)
    session.commit()
    return {"id": location_id, "deleted": True}


# ---------- items ----------

@router.get("/items")
def list_items(
    session: Session = Depends(get_session),
    q: str | None = None,
    brand: str | None = None,
    estante: int | None = None,
    prateleira: str | None = None,
    stock: Literal["all", "in_stock", "zero"] = "all",
    status: Literal["active", "inactive", "all"] = "active",
    sort: Literal["id", "description", "brand", "reference", "stock", "location", "verified"] = "id",
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    totals = (
        select(Stock.item_id.label("item_id"), func.sum(Stock.qty).label("total"))
        .group_by(Stock.item_id)
        .subquery()
    )
    total_col = func.coalesce(totals.c.total, 0)
    # Lowest rack and shelf among the item's stocked locations, for sorting by location.
    placed_at = (
        select(
            Stock.item_id.label("item_id"),
            func.min(Location.estante).label("estante"),
            func.min(Location.prateleira).label("prateleira"),
        )
        .join(Location, Location.id == Stock.location_id)
        .where(Stock.qty > 0)
        .group_by(Stock.item_id)
        .subquery()
    )
    stmt = (
        select(Item, total_col)
        .outerjoin(totals, totals.c.item_id == Item.id)
        .outerjoin(placed_at, placed_at.c.item_id == Item.id)
    )
    if status == "active":
        stmt = stmt.where(Item.active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(Item.active.is_(False))
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Item.description.ilike(term),
                Item.reference.ilike(term),
                Item.ean.ilike(term),
                Item.brand.ilike(term),
                cast(Item.id, String).ilike(term),
            )
        )
    if brand:
        stmt = stmt.where(Item.brand == brand)
    if estante is not None or prateleira is not None:
        present = (
            select(Stock.item_id)
            .join(Location, Location.id == Stock.location_id)
            .where(Stock.qty > 0)
        )
        if estante is not None:
            present = present.where(Location.estante == estante)
        if prateleira is not None:
            present = present.where(Location.prateleira == prateleira)
        stmt = stmt.where(Item.id.in_(present))
    if stock == "in_stock":
        stmt = stmt.where(total_col > 0)
    elif stock == "zero":
        stmt = stmt.where(total_col == 0)

    sort_keys = {
        "id": [Item.id],
        "description": [func.lower(Item.description)],
        "brand": [func.lower(Item.brand)],
        "reference": [func.lower(Item.reference)],
        "stock": [total_col],
        "location": [placed_at.c.estante, placed_at.c.prateleira],
        "verified": [Item.verified_at],
    }
    direction = (lambda c: c.asc().nulls_last()) if order == "asc" else (lambda c: c.desc().nulls_last())
    order_by = [direction(expr) for expr in sort_keys[sort]] + [Item.id]

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(stmt.order_by(*order_by).limit(limit).offset(offset)).all()

    ids = [item.id for item, _ in rows]
    placed: dict[int, list[str]] = {}
    if ids:
        for stock_row, loc in session.execute(
            select(Stock, Location)
            .join(Location, Location.id == Stock.location_id)
            .where(Stock.item_id.in_(ids), Stock.qty > 0)
            .order_by(Location.estante, Location.prateleira)
        ).all():
            placed.setdefault(stock_row.item_id, []).append(f"{loc.label} ({stock_row.qty})")

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": item.id,
                "description": item.description,
                "brand": item.brand,
                "reference": item.reference,
                "ean": item.ean,
                "active": item.active,
                "stock_total": int(total_qty),
                "locations": placed.get(item.id, []),
                "verified_at": _iso(item.verified_at),
            }
            for item, total_qty in rows
        ],
    }


@router.post("/items", status_code=201)
def create_item(body: ItemCreate, session: Session = Depends(get_session)):
    description = body.description.strip()
    if not description:
        raise HTTPException(status_code=422, detail="A descrição é obrigatória")
    item_id = body.id
    if item_id is None:
        item_id = (session.scalar(select(func.max(Item.id))) or 0) + 1
    if session.get(Item, item_id) is not None:
        raise HTTPException(status_code=409, detail=f"Já existe um item com o id {item_id}")
    session.add(
        Item(
            id=item_id,
            description=description,
            brand=_blank(body.brand),
            reference=_blank(body.reference),
            ean=_blank(body.ean),
            serial_number=_blank(body.serial_number),
            notes=_blank(body.notes),
        )
    )
    session.commit()
    if body.initial_qty:
        apply_movement(
            session,
            type="IN",
            item_id=item_id,
            qty=body.initial_qty,
            to_location_id=body.initial_location_id,
            reason="Stock inicial",
            source="local",
        )
    return {"id": item_id}


@router.get("/items/{item_id}")
def get_item(item_id: int, session: Session = Depends(get_session)):
    item = _item_or_404(session, item_id)
    labels = _location_labels(session)
    voided = _voided_ids(session)
    stock_rows = session.execute(
        select(Stock, Location)
        .join(Location, Location.id == Stock.location_id)
        .where(Stock.item_id == item_id, Stock.qty > 0)
        .order_by(Location.estante, Location.prateleira)
    ).all()
    movements = session.scalars(
        select(Movement).where(Movement.item_id == item_id).order_by(Movement.created_at.desc()).limit(50)
    ).all()
    return {
        "id": item.id,
        "description": item.description,
        "brand": item.brand,
        "reference": item.reference,
        "ean": item.ean,
        "serial_number": item.serial_number,
        "notes": item.notes,
        "active": item.active,
        "verified_at": _iso(item.verified_at),
        "stock_total": item_total(session, item_id),
        "stock": [
            {"location_id": s.location_id, "location": loc.label, "qty": s.qty}
            for s, loc in stock_rows
        ],
        "movements": [_movement_dict(m, labels, voided) for m in movements],
    }


@router.patch("/items/{item_id}")
def update_item(item_id: int, patch: ItemPatch, session: Session = Depends(get_session)):
    item = _item_or_404(session, item_id)
    changes = patch.model_dump(exclude_unset=True)
    if "description" in changes:
        description = (changes["description"] or "").strip()
        if not description:
            raise HTTPException(status_code=422, detail="A descrição não pode estar vazia")
        changes["description"] = description
    if changes.get("active") is False and item_total(session, item_id) > 0:
        raise HTTPException(status_code=422, detail="Remova o stock antes de eliminar o item")
    verified = changes.pop("verified", None)
    if verified is False:
        item.verified_at = None
    elif verified is True and item.verified_at is None:
        item.verified_at = utcnow()
    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(item, field, value)
    session.commit()
    return {"id": item.id, "updated": sorted(changes)}


@router.delete("/items/{item_id}")
def delete_item(item_id: int, session: Session = Depends(get_session)):
    """Soft delete: the item is deactivated and its history is kept. Requires zero stock."""
    item = _item_or_404(session, item_id)
    if item_total(session, item_id) > 0:
        raise HTTPException(status_code=422, detail="Remova o stock antes de eliminar o item")
    item.active = False
    session.commit()
    return {"id": item.id, "active": False}


# ---------- movements ----------

@router.post("/movements", status_code=201)
def create_movement(body: MovementIn, session: Session = Depends(get_session)):
    try:
        movement = apply_movement(
            session,
            type=body.type,
            item_id=body.item_id,
            qty=body.qty,
            from_location_id=body.from_location_id,
            to_location_id=body.to_location_id,
            reason=body.reason,
            operator=body.operator,
            source="local",
        )
    except MovementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if movement is None:
        return {"changed": False}
    return {
        "changed": True,
        "movement": _movement_dict(movement, _location_labels(session), _voided_ids(session)),
    }


@router.post("/movements/{movement_id}/void", status_code=201)
def void_movement_route(movement_id: str, body: VoidIn | None = None, session: Session = Depends(get_session)):
    try:
        reversal = void_movement(session, movement_id, operator=(body.operator if body else None))
    except MovementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if reversal is None:
        return {"changed": False}
    return {
        "changed": True,
        "movement": _movement_dict(reversal, _location_labels(session), _voided_ids(session)),
    }


@router.get("/movements")
def list_movements(
    session: Session = Depends(get_session),
    item_id: int | None = None,
    type: str | None = None,
    source: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    stmt = select(Movement).order_by(Movement.created_at.desc())
    if item_id is not None:
        stmt = stmt.where(Movement.item_id == item_id)
    if type:
        stmt = stmt.where(Movement.type == type)
    if source:
        stmt = stmt.where(Movement.source == source)
    labels = _location_labels(session)
    voided = _voided_ids(session)
    return [_movement_dict(m, labels, voided) for m in session.scalars(stmt.limit(limit)).all()]


# ---------- export ----------

EXPORT_COLUMNS = [
    "DESCRICAO", "MARCA", "REFERENCIA", "id", "QTD_STOCK",
    "PRATELEIRA", "ESTANTE", "S_N", "EAN", "Verificado",
]


def _local_date(value: datetime | None) -> str | None:
    """Verified date as YYYY-MM-DD in local time. Stored datetimes are UTC (naive on SQLite)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().date().isoformat()


@router.get("/export/xlsx")
def export_xlsx(session: Session = Depends(get_session)):
    """Builds the inventory workbook from the database, in the layout of the imported sheet.

    One row per item and stocked location; items with no stock get one row with quantity 0.
    Inactive items are left out.
    """
    stamp = datetime.now()
    items = session.scalars(select(Item).where(Item.active.is_(True)).order_by(Item.id)).all()
    placed: dict[int, list[tuple[Location, int]]] = {}
    for stock_row, loc in session.execute(
        select(Stock, Location).join(Location, Location.id == Stock.location_id).where(Stock.qty > 0)
    ).all():
        placed.setdefault(stock_row.item_id, []).append((loc, stock_row.qty))

    wb = Workbook()
    ws = wb.active
    ws.title = f"INVENTARIO {stamp:%Y%m%d-%H%M%S}"[:31]  # Excel limits sheet names to 31 characters
    ws.append(EXPORT_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    for item in items:
        placements = sorted(
            placed.get(item.id, []),
            key=lambda p: (p[0].estante or 0, p[0].prateleira or ""),
        ) or [(None, 0)]
        verified = _local_date(item.verified_at)
        for loc, qty in placements:
            located = loc is not None and loc.id != UNASSIGNED_LOCATION_ID
            ws.append([
                item.description,
                item.brand,
                item.reference,
                item.id,
                qty,
                loc.prateleira if located else None,
                loc.estante if located else None,
                item.serial_number,
                item.ean,
                verified,
            ])

    for index, width in enumerate([48, 18, 20, 8, 12, 14, 10, 20, 16, 14], start=1):
        ws.column_dimensions[ws.cell(row=1, column=index).column_letter].width = width

    buffer = BytesIO()
    wb.save(buffer)
    filename = f"Inventario-{stamp:%Y%m%d-%H%M%S}.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- local data reset ----------

CLEAR_CONFIRMATIONS = ("APAGAR", "DELETE")


class ClearDataIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: str


@router.post("/admin/clear-data")
def clear_local_data(body: ClearDataIn, session: Session = Depends(get_session)):
    """Deletes all inventory data stored on this PC so a fresh import can start.

    Keeps the SharePoint sign-in, the file link and the reserved 'Sem localização' location.
    The SharePoint workbook itself is not touched.
    """
    if body.confirm.strip().upper() not in CLEAR_CONFIRMATIONS:
        raise HTTPException(status_code=422, detail="Escreva APAGAR para confirmar")
    try:
        deleted = {
            "movements": session.execute(delete(Movement)).rowcount,
            "stock": session.execute(delete(Stock)).rowcount,
            "items": session.execute(delete(Item)).rowcount,
            "locations": session.execute(
                delete(Location).where(Location.id != UNASSIGNED_LOCATION_ID)
            ).rowcount,
            "sync_runs": session.execute(delete(SyncRun)).rowcount,
        }
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"cleared": True, "deleted": deleted}


# ---------- SharePoint ----------

def _sharepoint(request: Request):
    service = getattr(request.app.state, "sharepoint", None)
    if service is None:
        raise HTTPException(
            status_code=422,
            detail="SharePoint não configurado: defina client_id em data/sharepoint.json",
        )
    return service


@router.get("/sharepoint/status")
def sharepoint_status(request: Request):
    service = getattr(request.app.state, "sharepoint", None)
    if service is None:
        return {"configured": False}
    return service.status()


@router.post("/sharepoint/sign-in")
def sharepoint_sign_in(request: Request):
    service = _sharepoint(request)
    try:
        return service.begin_sign_in()
    except SharePointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ShareUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_url: str


@router.put("/sharepoint/settings")
def sharepoint_settings(body: ShareUrlIn, request: Request):
    service = _sharepoint(request)
    try:
        service.set_share_url(body.share_url)
    except SharePointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return service.status()


@router.post("/sharepoint/sign-out")
def sharepoint_sign_out(request: Request):
    service = _sharepoint(request)
    service.sign_out()
    return service.status()


@router.post("/sharepoint/import/{mode}")
async def sharepoint_import(mode: Literal["dry-run", "commit"], request: Request):
    service = _sharepoint(request)
    try:
        name, data = service.download_workbook()
    except SharePointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.write(data)
    tmp.close()
    path = Path(tmp.name)
    try:
        if mode == "dry-run":
            report = importer.analyse(path, None)
        else:
            with request.app.state.session_factory() as session:
                report = importer.commit(session, path, None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
    return {**report.as_dict(), "source": f"SharePoint: {name}"}


# ---------- import ----------

async def _save_upload(file: UploadFile) -> Path:
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=422, detail="Envie um ficheiro .xlsx")
    data = await file.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


@router.post("/import/dry-run")
async def import_dry_run(file: UploadFile = File(...), sheet: str | None = Form(None)):
    path = await _save_upload(file)
    try:
        return importer.analyse(path, sheet or None).as_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@router.post("/import/commit")
async def import_commit(
    request: Request,
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
):
    path = await _save_upload(file)
    try:
        with request.app.state.session_factory() as session:
            return importer.commit(session, path, sheet or None).as_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
