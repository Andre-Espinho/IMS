import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ItemSummary, Location } from '../api'
import { errorMessage, formatDate, useI18n } from '../i18n'

const PAGE_SIZE = 50

type SortKey = 'id' | 'description' | 'brand' | 'reference' | 'stock' | 'location' | 'verified'

type Props = {
  locations: Location[]
  onOpen: (id: number) => void
  onNew: () => void
  refreshKey: number
}

export function ItemsPage({ locations, onOpen, onNew, refreshKey }: Props) {
  const { t, locale } = useI18n()
  const [q, setQ] = useState('')
  const [stock, setStock] = useState<'all' | 'in_stock' | 'zero'>('all')
  const [status, setStatus] = useState<'active' | 'inactive' | 'all'>('active')
  const [sort, setSort] = useState<SortKey>('id')
  const [order, setOrder] = useState<'asc' | 'desc'>('asc')
  const [estante, setEstante] = useState('')
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<ItemSummary[]>([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const estantes = [...new Set(locations.map((l) => l.estante).filter((e): e is number => e !== null))].sort(
    (a, b) => a - b,
  )

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      try {
        const data = await api.listItems({
          q: q.trim() || undefined,
          stock,
          status,
          sort,
          order,
          estante: estante || undefined,
          limit: PAGE_SIZE,
          offset,
        })
        if (!cancelled) {
          setItems(data.items)
          setTotal(data.total)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err, t, 'errors.loadItems'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    const timer = setTimeout(load, 200) // debounce typing
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
    // t is stable per locale; include locale so error text follows the language.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, stock, status, estante, sort, order, offset, refreshKey, locale])

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + PAGE_SIZE, total)

  // Click a header: new column sorts ascending; same column flips the direction.
  function toggleSort(key: SortKey) {
    if (sort === key) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSort(key)
      setOrder('asc')
    }
    setOffset(0)
  }

  function sortHeader(key: SortKey, label: string, className = '') {
    const active = sort === key
    return (
      <th
        className={`sortable ${className} ${active ? 'sorted' : ''}`}
        onClick={() => toggleSort(key)}
        aria-sort={active ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        {label}
        <span className="sort-arrow">{active ? (order === 'asc' ? ' ▲' : ' ▼') : ' ↕'}</span>
      </th>
    )
  }

  return (
    <section>
      <header className="page-header">
        <h1>{t('items.title')}</h1>
        <span className="muted">{t('items.count', { count: total })}</span>
        <button className="primary push-right" onClick={onNew}>
          {t('items.new')}
        </button>
      </header>

      <div className="toolbar">
        <input
          className="search"
          placeholder={t('items.search')}
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setOffset(0)
          }}
        />
        <select
          value={stock}
          onChange={(e) => {
            setStock(e.target.value as typeof stock)
            setOffset(0)
          }}
        >
          <option value="all">{t('items.stock.all')}</option>
          <option value="in_stock">{t('items.stock.in')}</option>
          <option value="zero">{t('items.stock.zero')}</option>
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as typeof status)
            setOffset(0)
          }}
        >
          <option value="active">{t('items.status.active')}</option>
          <option value="inactive">{t('items.status.inactive')}</option>
          <option value="all">{t('items.status.all')}</option>
        </select>
        <select
          value={estante}
          onChange={(e) => {
            setEstante(e.target.value)
            setOffset(0)
          }}
        >
          <option value="">{t('items.shelf.all')}</option>
          {estantes.map((e) => (
            <option key={e} value={e}>
              {t('items.shelf.label', { n: e })}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {sortHeader('id', t('items.col.id'))}
              {sortHeader('description', t('items.col.description'))}
              {sortHeader('brand', t('items.col.brand'))}
              {sortHeader('reference', t('items.col.reference'))}
              {sortHeader('stock', t('items.col.stock'), 'num')}
              {sortHeader('location', t('items.col.location'))}
              {sortHeader('verified', t('items.col.verified'))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} onClick={() => onOpen(item.id)} className="clickable">
                <td>{item.id}</td>
                <td className="desc">{item.description}</td>
                <td>{item.brand ?? t('common.none')}</td>
                <td>{item.reference ?? t('common.none')}</td>
                <td className={`num ${item.stock_total === 0 ? 'zero' : ''}`}>{item.stock_total}</td>
                <td>{item.locations.join(', ') || t('items.noLocation')}</td>
                <td>{formatDate(item.verified_at, locale)}</td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="muted center">
                  {t('items.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <footer className="pager">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          {t('common.previous')}
        </button>
        <span className="muted">{t('items.range', { from, to, total })}</span>
        <button disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          {t('common.next')}
        </button>
      </footer>
    </section>
  )
}
