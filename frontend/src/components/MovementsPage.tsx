import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Movement, MovementType } from '../api'
import { errorMessage, formatDate, movementTypeLabel, sourceLabel, useI18n } from '../i18n'

type Props = {
  refreshKey: number
  onOpenItem: (id: number) => void
}

const MOVEMENT_TYPES: MovementType[] = ['IN', 'OUT', 'MOVE', 'ADJUST', 'VERIFY']
const SOURCES: Movement['source'][] = ['local', 'mobile', 'import']

export function MovementsPage({ refreshKey, onOpenItem }: Props) {
  const { t, locale } = useI18n()
  const [type, setType] = useState<MovementType | ''>('')
  const [source, setSource] = useState<Movement['source'] | ''>('')
  const [rows, setRows] = useState<Movement[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .movements({ type: type || undefined, source: source || undefined, limit: 200 })
      .then((data) => {
        if (!cancelled) {
          setRows(data)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, t, 'errors.loadMovements'))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, source, refreshKey, locale])

  return (
    <section>
      <header className="page-header">
        <h1>{t('movements.title')}</h1>
      </header>

      <div className="toolbar">
        <select value={type} onChange={(e) => setType(e.target.value as MovementType | '')}>
          <option value="">{t('movements.allTypes')}</option>
          {MOVEMENT_TYPES.map((mt) => (
            <option key={mt} value={mt}>
              {movementTypeLabel(t, mt)}
            </option>
          ))}
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value as Movement['source'] | '')}>
          <option value="">{t('movements.allSources')}</option>
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {sourceLabel(t, s)}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('movements.col.date')}</th>
              <th>{t('movements.col.type')}</th>
              <th>{t('movements.col.item')}</th>
              <th className="num">{t('movements.col.qty')}</th>
              <th>{t('movements.col.fromTo')}</th>
              <th>{t('movements.col.operator')}</th>
              <th>{t('movements.col.source')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id} className="clickable" onClick={() => onOpenItem(m.item_id)}>
                <td>{formatDate(m.created_at, locale)}</td>
                <td>{movementTypeLabel(t, m.type)}</td>
                <td>#{m.item_id}</td>
                <td className="num">{m.type === 'ADJUST' && m.qty > 0 ? `+${m.qty}` : m.qty}</td>
                <td>
                  {m.from_location ?? t('common.none')} → {m.to_location ?? t('common.none')}
                </td>
                <td>{m.operator ?? t('common.none')}</td>
                <td>{sourceLabel(t, m.source)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="muted center">
                  {t('movements.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
