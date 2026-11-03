"""Stock movement rules. See docs/SPEC.md §5.

Every public function runs in one transaction: it commits on success and rolls
back on any error. Movements are append-only; corrections are new movements.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import UNASSIGNED_LOCATION_ID, Item, Location, Movement, Stock, utcnow

MOVEMENT_TYPES = ("IN", "OUT", "MOVE", "ADJUST", "VERIFY")
SOURCES = ("local", "mobile", "import")

_LABEL_RE = re.compile(r"^E(\d+)-(P(\d+)|Topo)$", re.IGNORECASE)


class MovementError(ValueError):
    """A business-rule violation. The message is shown to the operator (in Portuguese)."""


def parse_label(label: str) -> tuple[int, str]:
    """'E5-P4' -> (5, '4'); 'E3-Topo' -> (3, 'Topo')."""
    match = _LABEL_RE.match(label.strip())
    if not match:
        raise MovementError(f"Localização inválida: {label}")
    estante = int(match.group(1))
    prateleira = "Topo" if match.group(2).lower() == "topo" else match.group(3)
    return estante, prateleira


def find_or_create_location(session: Session, estante: int | None, prateleira: str | None) -> Location:
    if estante is None and prateleira is None:
        return require_location(session, UNASSIGNED_LOCATION_ID)
    location = session.scalar(
        select(Location).where(Location.estante == estante, Location.prateleira == prateleira)
    )
    if location is None:
        next_id = (session.scalar(select(func.max(Location.id))) or 0) + 1
        location = Location(id=next_id, estante=estante, prateleira=prateleira)
        session.add(location)
        session.flush()
    return location


def require_location(session: Session, location_id: int) -> Location:
    location = session.get(Location, location_id)
    if location is None:
        raise MovementError(f"Localização {location_id} não existe")
    return location


def _require_item(session: Session, item_id: int) -> Item:
    item = session.get(Item, item_id)
    if item is None or not item.active:
        raise MovementError(f"Item {item_id} não existe")
    return item


def _stock_row(session: Session, item_id: int, location_id: int) -> Stock:
    stock = session.get(Stock, (item_id, location_id))
    if stock is None:
        stock = Stock(item_id=item_id, location_id=location_id, qty=0)
        session.add(stock)
        session.flush()
    return stock


def _source_location(session: Session, item_id: int, given: int | None) -> int:
    if given is not None:
        return given
    stocked = session.scalars(select(Stock).where(Stock.item_id == item_id, Stock.qty > 0)).all()
    if len(stocked) == 1:
        return stocked[0].location_id
    raise MovementError("Indique a localização de origem (o item tem stock em mais de um sítio ou em nenhum)")


def _require_qty(qty: int | None, minimum: int = 1) -> int:
    if qty is None or qty < minimum:
        if minimum == 1:
            raise MovementError("A quantidade deve ser maior que zero")
        raise MovementError("A quantidade contada não pode ser negativa")
    return qty


def apply_movement(
    session: Session,
    *,
    type: str,
    item_id: int,
    qty: int | None = None,
    from_location_id: int | None = None,
    to_location_id: int | None = None,
    reason: str | None = None,
    operator: str | None = None,
    source: str = "local",
    external_ref: str | None = None,
) -> Movement | None:
    """Apply one movement. Returns the stored movement, or None when an ADJUST changes nothing."""
    if type not in MOVEMENT_TYPES:
        raise MovementError(f"Tipo de movimento inválido: {type}")
    if source not in SOURCES:
        raise MovementError(f"Origem inválida: {source}")

    try:
        _require_item(session, item_id)
        now = utcnow()
        common = dict(
            type=type,
            item_id=item_id,
            reason=(reason or "").strip() or None,
            operator=(operator or "").strip() or None,
            source=source,
            external_ref=external_ref,
            created_at=now,
        )

        if type == "VERIFY":
            session.get(Item, item_id).verified_at = now
            movement = Movement(qty=0, **common)
        elif type == "IN":
            qty = _require_qty(qty)
            dest = to_location_id if to_location_id is not None else UNASSIGNED_LOCATION_ID
            require_location(session, dest)
            _stock_row(session, item_id, dest).qty += qty
            movement = Movement(qty=qty, to_location_id=dest, **common)
        elif type == "OUT":
            qty = _require_qty(qty)
            src = _source_location(session, item_id, from_location_id)
            stock = _stock_row(session, item_id, src)
            if stock.qty < qty:
                raise MovementError(f"Stock insuficiente: há {stock.qty} no sítio de origem")
            stock.qty -= qty
            movement = Movement(qty=qty, from_location_id=src, **common)
        elif type == "MOVE":
            qty = _require_qty(qty)
            if from_location_id is None or to_location_id is None:
                raise MovementError("Indique a origem e o destino da transferência")
            if from_location_id == to_location_id:
                raise MovementError("A origem e o destino são iguais")
            require_location(session, to_location_id)
            src_stock = _stock_row(session, item_id, from_location_id)
            if src_stock.qty < qty:
                raise MovementError(f"Stock insuficiente: há {src_stock.qty} na origem")
            src_stock.qty -= qty
            _stock_row(session, item_id, to_location_id).qty += qty
            movement = Movement(qty=qty, from_location_id=from_location_id, to_location_id=to_location_id, **common)
        else:  # ADJUST: qty is the counted quantity at the location
            counted = _require_qty(qty, minimum=0)
            loc = to_location_id if to_location_id is not None else (
                from_location_id if from_location_id is not None else UNASSIGNED_LOCATION_ID
            )
            require_location(session, loc)
            stock = _stock_row(session, item_id, loc)
            delta = counted - stock.qty
            if delta == 0:
                session.commit()
                return None
            stock.qty = counted
            movement = Movement(qty=delta, to_location_id=loc, **common)

        session.add(movement)
        session.commit()
        return movement
    except Exception:
        session.rollback()
        raise


REVERSIBLE = ("IN", "OUT", "MOVE", "ADJUST")


def void_movement(session: Session, movement_id: str, operator: str | None = None) -> Movement | None:
    """Undo a movement by recording a reversing movement. The original stays in the log.

    The reversal's external_ref is 'void:<original id>', which doubles as the
    'already voided' marker (external_ref is unique).
    """
    original = session.get(Movement, movement_id)
    if original is None:
        raise MovementError("Movimento não existe")
    if original.type not in REVERSIBLE:
        raise MovementError("Este tipo de movimento não pode ser anulado")
    marker = f"void:{original.id}"
    if session.scalar(select(Movement.id).where(Movement.external_ref == marker)):
        raise MovementError("Este movimento já foi anulado")

    common = dict(
        item_id=original.item_id,
        operator=operator,
        reason=f"Anulação do movimento {original.id}",
        external_ref=marker,
    )
    if original.type == "IN":
        return apply_movement(session, type="OUT", qty=original.qty,
                              from_location_id=original.to_location_id, **common)
    if original.type == "OUT":
        return apply_movement(session, type="IN", qty=original.qty,
                              to_location_id=original.from_location_id, **common)
    if original.type == "MOVE":
        return apply_movement(session, type="MOVE", qty=original.qty,
                              from_location_id=original.to_location_id,
                              to_location_id=original.from_location_id, **common)
    # ADJUST: restore the quantity that was there before the adjustment.
    loc = original.to_location_id
    current = session.scalar(
        select(Stock.qty).where(Stock.item_id == original.item_id, Stock.location_id == loc)
    ) or 0
    previous = current - original.qty
    if previous < 0:
        raise MovementError("Não é possível anular: o stock atual já não permite esta reposição")
    return apply_movement(session, type="ADJUST", qty=previous, to_location_id=loc, **common)


def item_total(session: Session, item_id: int) -> int:
    return session.scalar(select(func.coalesce(func.sum(Stock.qty), 0)).where(Stock.item_id == item_id)) or 0
