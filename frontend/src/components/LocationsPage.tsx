import { useEffect, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { api } from '../api'
import type { Location } from '../api'
import { errorMessage, useI18n } from '../i18n'

type Props = {
  onChanged: () => void
}

const UNASSIGNED_ID = 0

export function LocationsPage({ onChanged }: Props) {
  const { t, locale } = useI18n()
  const [rows, setRows] = useState<Location[]>([])
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState(false)

  // New location form (rack and shelf only)
  const [newEstante, setNewEstante] = useState('')
  const [newPrateleira, setNewPrateleira] = useState('')

  // Inline edit: one row at a time. The Location text box edits the label.
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editEstante, setEditEstante] = useState('')
  const [editPrateleira, setEditPrateleira] = useState('')

  useEffect(() => {
    let cancelled = false
    api
      .locations()
      .then((data) => {
        if (!cancelled) setRows(data)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, t, 'errors.locations'))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, locale])

  async function act(action: () => Promise<unknown>, successKey: 'locations.notice.saved' | 'locations.notice.deleted') {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await action()
      setNotice(t(successKey))
      setReload((n) => n + 1)
      onChanged()
      return true
    } catch (err) {
      setError(errorMessage(err, t, 'errors.save'))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault()
    const ok = await act(
      () => api.createLocation({ estante: Number(newEstante), prateleira: newPrateleira.trim() || null }),
      'locations.notice.saved',
    )
    if (ok) {
      setNewEstante('')
      setNewPrateleira('')
    }
  }

  function startEdit(loc: Location) {
    setEditingId(loc.id)
    setEditLabel(loc.label)
    setEditEstante(String(loc.estante ?? ''))
    setEditPrateleira(loc.prateleira ?? '')
    setError(null)
    setNotice(null)
  }

  // If the Location text is left as it was shown, keep the stored name (or none),
  // so changing rack or shelf still updates the derived label. Otherwise the typed text is the name.
  async function saveEdit(loc: Location) {
    const typed = editLabel.trim()
    const name = typed === loc.label ? loc.name : typed || null
    const ok = await act(
      () =>
        api.updateLocation(loc.id, {
          name,
          estante: Number(editEstante),
          prateleira: editPrateleira.trim() || null,
        }),
      'locations.notice.saved',
    )
    if (ok) setEditingId(null)
  }

  function onEditKey(e: KeyboardEvent, loc: Location) {
    if (e.key === 'Enter') saveEdit(loc)
    if (e.key === 'Escape') setEditingId(null)
  }

  function remove(id: number) {
    if (!window.confirm(t('locations.deleteConfirm'))) return
    act(() => api.deleteLocation(id), 'locations.notice.deleted')
  }

  return (
    <section>
      <header className="page-header">
        <h1>{t('locations.title')}</h1>
      </header>

      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <form className="card location-form" onSubmit={create}>
        <h2 className="wide">{t('locations.new')}</h2>
        <label>
          {t('locations.estante')}
          <input type="number" min={1} value={newEstante} onChange={(e) => setNewEstante(e.target.value)} required />
        </label>
        <label>
          {t('locations.prateleira')}
          <input
            value={newPrateleira}
            onChange={(e) => setNewPrateleira(e.target.value)}
            placeholder={t('locations.prateleiraHint')}
          />
        </label>
        <button type="submit" className="primary" disabled={busy}>
          {t('locations.add')}
        </button>
      </form>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('locations.col.label')}</th>
              <th>{t('locations.estante')}</th>
              <th>{t('locations.prateleira')}</th>
              <th>{t('locations.col.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((loc) =>
              editingId === loc.id ? (
                <tr key={loc.id}>
                  <td>
                    <input
                      value={editLabel}
                      onChange={(e) => setEditLabel(e.target.value)}
                      onKeyDown={(e) => onEditKey(e, loc)}
                      className="wide-input"
                      autoFocus
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={1}
                      value={editEstante}
                      onChange={(e) => setEditEstante(e.target.value)}
                      onKeyDown={(e) => onEditKey(e, loc)}
                      className="narrow"
                    />
                  </td>
                  <td>
                    <input
                      value={editPrateleira}
                      onChange={(e) => setEditPrateleira(e.target.value)}
                      onKeyDown={(e) => onEditKey(e, loc)}
                      placeholder={t('locations.noShelf')}
                      className="narrow"
                    />
                  </td>
                  <td className="row-actions">
                    <button className="small primary" onClick={() => saveEdit(loc)} disabled={busy}>
                      {t('form.save')}
                    </button>
                    <button className="small" onClick={() => setEditingId(null)} disabled={busy}>
                      {t('form.cancel')}
                    </button>
                  </td>
                </tr>
              ) : (
                <tr key={loc.id}>
                  <td>{loc.label}</td>
                  <td>{loc.estante ?? t('common.none')}</td>
                  <td>{loc.prateleira ?? t('locations.noShelf')}</td>
                  <td className="row-actions">
                    {loc.id === UNASSIGNED_ID ? (
                      <span className="muted">{t('locations.unassignedNote')}</span>
                    ) : (
                      <>
                        <button className="small" onClick={() => startEdit(loc)} disabled={busy}>
                          {t('locations.edit')}
                        </button>
                        <button className="small danger" onClick={() => remove(loc.id)} disabled={busy}>
                          {t('locations.delete')}
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ),
            )}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="muted center">
                  {t('locations.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
