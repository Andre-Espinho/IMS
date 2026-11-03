import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { ItemDetail as Detail, Location, MovementType } from '../api'
import { errorMessage, formatDate, movementTypeLabel, sourceLabel, useI18n } from '../i18n'
import { ItemForm } from './ItemForm'

type Props = {
  itemId: number
  locations: Location[]
  onBack: () => void
  onChanged: () => void
}

const OPERATOR_KEY = 'ims.operator'
const MOVEMENT_TYPES: MovementType[] = ['IN', 'OUT', 'MOVE', 'ADJUST', 'VERIFY']

function rememberedOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) ?? ''
  } catch {
    return ''
  }
}

function rememberOperator(value: string) {
  try {
    localStorage.setItem(OPERATOR_KEY, value)
  } catch {
    /* storage unavailable: nothing to remember */
  }
}

export function ItemDetail({ itemId, locations, onBack, onChanged }: Props) {
  const { t, locale } = useI18n()
  const [item, setItem] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [editing, setEditing] = useState(false)

  // Movement form
  const [type, setType] = useState<MovementType>('IN')
  const [qty, setQty] = useState('')
  const [fromLoc, setFromLoc] = useState('')
  const [toLoc, setToLoc] = useState('')
  const [reason, setReason] = useState('')
  const [operator, setOperator] = useState(rememberedOperator)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .item(itemId)
      .then((data) => {
        if (!cancelled) {
          setItem(data)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, t, 'errors.loadItem'))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemId, reload, locale])

  if (error && !item) {
    return (
      <section>
        <button onClick={onBack}>{t('common.back')}</button>
        <p className="error">{error}</p>
      </section>
    )
  }
  if (!item) return <p className="muted">{t('common.loading')}</p>

  if (editing) {
    return (
      <ItemForm
        item={item}
        locations={locations}
        onCancel={() => setEditing(false)}
        onSaved={() => {
          setEditing(false)
          setNotice(t('item.notice.saved'))
          setReload((n) => n + 1)
          onChanged()
        }}
      />
    )
  }

  const needsFrom = type === 'OUT' || type === 'MOVE'
  const needsTo = type === 'IN' || type === 'MOVE' || type === 'ADJUST'
  const needsQty = type !== 'VERIFY'

  // Runs an action, shows the notice, reloads and tells the parent that stock may have changed.
  type SuccessKey =
    | 'item.notice.verified'
    | 'item.notice.unverified'
    | 'item.notice.deleted'
    | 'item.notice.reactivated'
    | 'item.notice.voided'
  type ErrorKey = 'errors.verify' | 'errors.delete' | 'errors.void' | 'errors.save'

  async function run(action: () => Promise<unknown>, successKey: SuccessKey, errorKey: ErrorKey) {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await action()
      setNotice(t(successKey))
      setReload((n) => n + 1)
      onChanged()
    } catch (err) {
      setError(errorMessage(err, t, errorKey))
    } finally {
      setBusy(false)
    }
  }

  async function submitMovement(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const result = await api.movement({
        type,
        item_id: itemId,
        qty: needsQty ? Number(qty) : undefined,
        from_location_id: needsFrom && fromLoc ? Number(fromLoc) : undefined,
        to_location_id: needsTo && toLoc ? Number(toLoc) : undefined,
        reason: reason.trim() || undefined,
        operator: operator.trim() || undefined,
      })
      rememberOperator(operator.trim())
      setNotice(result.changed ? t('item.notice.recorded') : t('item.notice.nochange'))
      setQty('')
      setReason('')
      setReload((n) => n + 1)
      onChanged()
    } catch (err) {
      setError(errorMessage(err, t, 'errors.register'))
    } finally {
      setBusy(false)
    }
  }

  function verify() {
    return run(
      () => api.movement({ type: 'VERIFY', item_id: itemId, operator: operator.trim() || undefined }),
      'item.notice.verified',
      'errors.verify',
    )
  }

  function unverify() {
    return run(() => api.updateItem(itemId, { verified: false }), 'item.notice.unverified', 'errors.save')
  }

  function remove() {
    if (!window.confirm(t('item.deleteConfirm'))) return
    return run(() => api.deleteItem(itemId), 'item.notice.deleted', 'errors.delete')
  }

  function reactivate() {
    return run(() => api.updateItem(itemId, { active: true }), 'item.notice.reactivated', 'errors.save')
  }

  function voidRow(movementId: string) {
    if (!window.confirm(t('item.voidConfirm'))) return
    return run(
      () => api.voidMovement(movementId, operator.trim() || undefined),
      'item.notice.voided',
      'errors.void',
    )
  }

  const hasStock = item.stock_total > 0

  return (
    <section>
      <button onClick={onBack}>{t('common.backToList')}</button>

      <header className="page-header">
        <h1>
          #{item.id} {item.description}
        </h1>
        {!item.active && <span className="badge">{t('item.inactive')}</span>}
      </header>

      <div className="actions">
        <button onClick={() => setEditing(true)} disabled={busy || !item.active}>
          {t('item.edit')}
        </button>
        {item.active ? (
          <button
            className="danger"
            onClick={remove}
            disabled={busy || hasStock}
            title={hasStock ? t('item.deleteBlocked') : undefined}
          >
            {t('item.delete')}
          </button>
        ) : (
          <button onClick={reactivate} disabled={busy}>
            {t('item.reactivate')}
          </button>
        )}
      </div>

      {notice && <p className="notice">{notice}</p>}
      {error && <p className="error">{error}</p>}

      <div className="grid-2">
        <div className="card">
          <h2>{t('item.data')}</h2>
          <dl className="facts">
            <dt>{t('item.fact.brand')}</dt>
            <dd>{item.brand ?? t('common.none')}</dd>
            <dt>{t('item.fact.reference')}</dt>
            <dd>{item.reference ?? t('common.none')}</dd>
            <dt>{t('item.fact.ean')}</dt>
            <dd>{item.ean ?? t('common.none')}</dd>
            <dt>{t('item.fact.serial')}</dt>
            <dd>{item.serial_number ?? t('common.none')}</dd>
            <dt>{t('item.fact.verified')}</dt>
            <dd>{formatDate(item.verified_at, locale)}</dd>
          </dl>
          {item.notes && <p className="notes">{item.notes}</p>}
          {item.verified_at ? (
            <button onClick={unverify} disabled={busy || !item.active}>
              {t('item.unverifyButton')}
            </button>
          ) : (
            <button onClick={verify} disabled={busy || !item.active}>
              {t('item.verifyButton')}
            </button>
          )}
        </div>

        <div className="card">
          <h2>{t('item.stockTitle', { total: item.stock_total })}</h2>
          {item.stock.length === 0 ? (
            <p className="muted">{t('item.noStock')}</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t('item.col.location')}</th>
                  <th className="num">{t('item.col.qty')}</th>
                </tr>
              </thead>
              <tbody>
                {item.stock.map((s) => (
                  <tr key={s.location_id}>
                    <td>{s.location}</td>
                    <td className="num">{s.qty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {item.active && (
        <div className="card">
          <h2>{t('item.record')}</h2>
          <form className="movement-form" onSubmit={submitMovement}>
            <label>
              {t('item.field.type')}
              <select value={type} onChange={(e) => setType(e.target.value as MovementType)}>
                {MOVEMENT_TYPES.map((mt) => (
                  <option key={mt} value={mt}>
                    {movementTypeLabel(t, mt)}
                  </option>
                ))}
              </select>
            </label>

            {needsQty && (
              <label>
                {type === 'ADJUST' ? t('item.field.counted') : t('item.field.qty')}
                <input
                  type="number"
                  min={type === 'ADJUST' ? 0 : 1}
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  required
                />
              </label>
            )}

            {needsFrom && (
              <label>
                {t('item.field.from')}
                <select value={fromLoc} onChange={(e) => setFromLoc(e.target.value)} required={type === 'MOVE'}>
                  <option value="">{type === 'OUT' ? t('item.from.auto') : t('item.pick')}</option>
                  {locations.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {needsTo && (
              <label>
                {type === 'MOVE'
                  ? t('item.field.to')
                  : type === 'ADJUST'
                    ? t('item.field.countedLocation')
                    : t('item.field.location')}
                <select value={toLoc} onChange={(e) => setToLoc(e.target.value)} required={type === 'MOVE'}>
                  <option value="">{type === 'MOVE' ? t('item.pick') : t('item.to.none')}</option>
                  {locations.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label className="wide">
              {t('item.field.reason')}
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t('common.optional')} />
            </label>

            <label>
              {t('item.field.operator')}
              <input
                value={operator}
                onChange={(e) => setOperator(e.target.value)}
                placeholder={t('item.namePlaceholder')}
              />
            </label>

            <button type="submit" disabled={busy}>
              {t('item.submit')}
            </button>
          </form>
        </div>
      )}

      <div className="card">
        <h2>{t('item.history')}</h2>
        {item.movements.length === 0 ? (
          <p className="muted">{t('item.noMovements')}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('item.col.date')}</th>
                <th>{t('item.col.type')}</th>
                <th className="num">{t('item.col.qty')}</th>
                <th>{t('item.col.fromTo')}</th>
                <th>{t('item.col.operator')}</th>
                <th>{t('item.col.source')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {item.movements.map((m) => (
                <tr key={m.id}>
                  <td>{formatDate(m.created_at, locale)}</td>
                  <td>{movementTypeLabel(t, m.type)}</td>
                  <td className="num">{m.type === 'ADJUST' && m.qty > 0 ? `+${m.qty}` : m.qty}</td>
                  <td>
                    {m.from_location ?? t('common.none')} → {m.to_location ?? t('common.none')}
                  </td>
                  <td>{m.operator ?? t('common.none')}</td>
                  <td>{sourceLabel(t, m.source)}</td>
                  <td>
                    {m.voidable && (
                      <button className="small" onClick={() => voidRow(m.id)} disabled={busy}>
                        {t('item.void')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  )
}
