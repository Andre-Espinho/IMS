import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Location } from './api'
import { I18nProvider, useI18n } from './i18n'
import type { Locale } from './i18n'
import { ItemsPage } from './components/ItemsPage'
import { ItemDetail } from './components/ItemDetail'
import { MovementsPage } from './components/MovementsPage'
import { ImportPage } from './components/ImportPage'
import { ItemForm } from './components/ItemForm'
import { LocationsPage } from './components/LocationsPage'
import './index.css'

type SimpleView = { name: 'items' } | { name: 'movements' } | { name: 'import' } | { name: 'locations' }
type View = SimpleView | { name: 'item'; id: number } | { name: 'item-new' }
type Theme = 'light' | 'dark'

const THEME_KEY = 'ims.theme'
const THEMES: { value: Theme; labelKey: 'theme.light' | 'theme.dark' }[] = [
  { value: 'light', labelKey: 'theme.light' },
  { value: 'dark', labelKey: 'theme.dark' },
]
const LOCALES: { value: Locale; label: string }[] = [
  { value: 'pt-PT', label: 'PT-PT' },
  { value: 'en-GB', label: 'EN-UK' },
]

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* storage unavailable: fall back to the system setting */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function Shell() {
  const { t, locale, setLocale } = useI18n()
  const [view, setView] = useState<View>({ name: 'items' })
  const [theme, setTheme] = useState<Theme>(initialTheme)
  const [locations, setLocations] = useState<Location[]>([])
  const [online, setOnline] = useState<boolean | null>(null)
  const [version, setVersion] = useState(0) // bumped whenever stock changes

  const bump = useCallback(() => setVersion((n) => n + 1), [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* storage unavailable: the choice just won't persist */
    }
  }, [theme])

  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  // The backend is started by Electron at the same time as this window, so the
  // first checks often fail. Retry quickly while offline, then check every 15 s.
  useEffect(() => {
    let cancelled = false
    let timer: number | undefined
    async function check() {
      let up = false
      try {
        await api.health()
        up = true
      } catch {
        up = false
      }
      if (cancelled) return
      setOnline(up)
      timer = window.setTimeout(check, up ? 15000 : 2000)
    }
    check()
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    if (online !== true) return
    api
      .locations()
      .then(setLocations)
      .catch(() => setLocations([]))
  }, [online, version])

  const nav = (target: SimpleView, label: string) => (
    <button
      className={`nav-link ${view.name === target.name ? 'active' : ''}`}
      onClick={() => setView(target)}
    >
      {label}
    </button>
  )

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">IMS</div>
        <nav>
          {nav({ name: 'items' }, t('nav.items'))}
          {nav({ name: 'movements' }, t('nav.movements'))}
          {nav({ name: 'locations' }, t('nav.locations'))}
          {nav({ name: 'import' }, t('nav.import'))}
        </nav>
        <div className={`status ${online === false ? 'offline' : ''}`}>
          {online === null ? t('status.connecting') : online ? t('status.online') : t('status.offline')}
        </div>
        <div className="sidebar-footer">
          <div className="segmented" role="group" aria-label={t('locale.label')}>
            {LOCALES.map((l) => (
              <button
                key={l.value}
                className={locale === l.value ? 'active' : ''}
                aria-pressed={locale === l.value}
                onClick={() => setLocale(l.value)}
              >
                {l.label}
              </button>
            ))}
          </div>
          <div className="segmented" role="group" aria-label={t('theme.label')}>
            {THEMES.map((th) => (
              <button
                key={th.value}
                className={theme === th.value ? 'active' : ''}
                aria-pressed={theme === th.value}
                onClick={() => setTheme(th.value)}
              >
                {t(th.labelKey)}
              </button>
            ))}
          </div>
        </div>
      </aside>

      <main className="content">
        {online !== true && <p className="muted">{t('status.waiting')}</p>}
        {online === true && view.name === 'items' && (
          <ItemsPage
            locations={locations}
            refreshKey={version}
            onOpen={(id) => setView({ name: 'item', id })}
            onNew={() => setView({ name: 'item-new' })}
          />
        )}
        {online === true && view.name === 'item-new' && (
          <ItemForm
            locations={locations}
            onCancel={() => setView({ name: 'items' })}
            onSaved={(id) => {
              bump()
              setView({ name: 'item', id })
            }}
          />
        )}
        {online === true && view.name === 'locations' && <LocationsPage onChanged={bump} />}
        {online === true && view.name === 'item' && (
          <ItemDetail
            key={view.id}
            itemId={view.id}
            locations={locations}
            onBack={() => setView({ name: 'items' })}
            onChanged={bump}
          />
        )}
        {online === true && view.name === 'movements' && (
          <MovementsPage refreshKey={version} onOpenItem={(id) => setView({ name: 'item', id })} />
        )}
        {online === true && view.name === 'import' && <ImportPage onCommitted={bump} />}
      </main>
    </div>
  )
}

function App() {
  return (
    <I18nProvider>
      <Shell />
    </I18nProvider>
  )
}

export default App
