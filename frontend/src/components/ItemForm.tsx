import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import type { ItemDetail, ItemInput, Location } from '../api'
import { errorMessage, useI18n } from '../i18n'

type Props = {
  /** Present when editing; absent when creating. */
  item?: ItemDetail
  locations: Location[]
  onSaved: (id: number) => void
  onCancel: () => void
}

export function ItemForm({ item, locations, onSaved, onCancel }: Props) {
  const { t } = useI18n()
  const isNew = !item
  const [id, setId] = useState('')
  const [description, setDescription] = useState(item?.description ?? '')
  const [brand, setBrand] = useState(item?.brand ?? '')
  const [reference, setReference] = useState(item?.reference ?? '')
  const [ean, setEan] = useState(item?.ean ?? '')
  const [serial, setSerial] = useState(item?.serial_number ?? '')
  const [notes, setNotes] = useState(item?.notes ?? '')
  const [initialQty, setInitialQty] = useState('')
  const [initialLoc, setInitialLoc] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!description.trim()) {
      setError(t('form.required'))
      return
    }
    const fields: ItemInput = {
      description: description.trim(),
      brand: brand.trim() || null,
      reference: reference.trim() || null,
      ean: ean.trim() || null,
      serial_number: serial.trim() || null,
      notes: notes.trim() || null,
    }
    setBusy(true)
    setError(null)
    try {
      if (item) {
        await api.updateItem(item.id, fields)
        onSaved(item.id)
      } else {
        const created = await api.createItem({
          ...fields,
          id: id.trim() ? Number(id) : undefined,
          initial_qty: initialQty ? Number(initialQty) : undefined,
          initial_location_id: initialLoc ? Number(initialLoc) : undefined,
        })
        onSaved(created.id)
      }
    } catch (err) {
      setError(errorMessage(err, t, 'errors.save'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <header className="page-header">
        <h1>{isNew ? t('form.new') : t('form.edit')}</h1>
      </header>

      {error && <p className="error">{error}</p>}

      <form className="card item-form" onSubmit={submit}>
        {isNew && (
          <label>
            {t('form.id')}
            <input type="number" min={1} value={id} onChange={(e) => setId(e.target.value)} />
          </label>
        )}
        <label className="wide">
          {t('form.description')} *
          <input value={description} onChange={(e) => setDescription(e.target.value)} required />
        </label>
        <label>
          {t('form.brand')}
          <input value={brand} onChange={(e) => setBrand(e.target.value)} />
        </label>
        <label>
          {t('form.reference')}
          <input value={reference} onChange={(e) => setReference(e.target.value)} />
        </label>
        <label>
          {t('form.ean')}
          <input value={ean} onChange={(e) => setEan(e.target.value)} />
        </label>
        <label>
          {t('form.serial')}
          <input value={serial} onChange={(e) => setSerial(e.target.value)} />
        </label>
        <label className="wide">
          {t('form.notes')}
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
        </label>

        {isNew && (
          <>
            <label>
              {t('form.initialQty')}
              <input type="number" min={0} value={initialQty} onChange={(e) => setInitialQty(e.target.value)} />
            </label>
            <label>
              {t('form.initialLocation')}
              <select value={initialLoc} onChange={(e) => setInitialLoc(e.target.value)}>
                <option value="">{t('item.to.none')}</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        <div className="form-actions wide">
          <button type="button" onClick={onCancel} disabled={busy}>
            {t('form.cancel')}
          </button>
          <button type="submit" disabled={busy}>
            {t('form.save')}
          </button>
        </div>
      </form>
    </section>
  )
}
