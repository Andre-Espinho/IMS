import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ImportReport } from '../api'
import { errorMessage, useI18n } from '../i18n'

type Source = 'local' | 'sharepoint'
type SpStatus = Awaited<ReturnType<typeof api.spStatus>>
type Report = ImportReport & { source?: string }

export function ImportPage({ onCommitted }: { onCommitted: () => void }) {
  const { t } = useI18n()
  const [source, setSource] = useState<Source>('local')
  const [file, setFile] = useState<File | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  // SharePoint sign-in state
  const [sp, setSp] = useState<SpStatus | null>(null)
  const [code, setCode] = useState<{ user_code: string; verification_uri: string } | null>(null)

  async function refreshSp() {
    try {
      setSp(await api.spStatus())
    } catch (err) {
      setSp({ configured: false, error: errorMessage(err, t, 'errors.import') })
    }
  }

  useEffect(() => {
    if (source === 'sharepoint') refreshSp()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source])

  // While the user is signing in, poll until the token is stored (or the flow fails).
  useEffect(() => {
    if (!sp?.pending) return
    const timer = window.setInterval(async () => {
      const next = await api.spStatus().catch(() => null)
      if (!next) return
      setSp(next)
      if (!next.pending) {
        if (next.signed_in) setCode(null)
        window.clearInterval(timer)
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [sp?.pending])

  // Delete local data (with a typed confirmation)
  const [clearOpen, setClearOpen] = useState(false)
  const [clearText, setClearText] = useState('')
  const [clearing, setClearing] = useState(false)

  async function clearData() {
    if (clearText.trim().toUpperCase() !== t('clear.word')) return
    setClearing(true)
    setError(null)
    setReport(null)
    try {
      await api.clearLocalData(clearText.trim())
      setDone(t('clear.done'))
      setClearOpen(false)
      setClearText('')
      setFile(null)
      onCommitted()
    } catch (err) {
      setError(errorMessage(err, t, 'errors.import'))
    } finally {
      setClearing(false)
    }
  }

  const [linkInput, setLinkInput] = useState('')
  const [linkNotice, setLinkNotice] = useState<string | null>(null)

  // Show the saved link once it is known, without overwriting what the user is typing.
  useEffect(() => {
    if (sp?.share_url) setLinkInput((current) => current || sp.share_url || '')
  }, [sp?.share_url])

  async function saveLink() {
    setError(null)
    setLinkNotice(null)
    try {
      await api.spSetLink(linkInput.trim())
      setLinkNotice(t('import.sp.linkSaved'))
      setReport(null)
      await refreshSp()
    } catch (err) {
      setError(errorMessage(err, t, 'errors.import'))
    }
  }

  async function signOut() {
    setError(null)
    setReport(null)
    setCode(null)
    try {
      await api.spSignOut()
      setLinkNotice(t('import.sp.signedOut'))
      await refreshSp()
    } catch (err) {
      setError(errorMessage(err, t, 'errors.import'))
    }
  }

  async function signIn() {
    setError(null)
    try {
      const started = await api.spSignIn()
      setCode(started)
      await refreshSp()
    } catch (err) {
      setError(errorMessage(err, t, 'errors.import'))
    }
  }

  function clearReport() {
    setReport(null)
    setDone(null)
    setError(null)
  }

  async function run(mode: 'dry-run' | 'commit') {
    if (source === 'local' && !file) return
    if (mode === 'commit' && !window.confirm(t('import.confirm'))) return
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      const result: Report =
        source === 'local' ? await api.importFile(mode, file as File) : await api.spImport(mode)
      setReport(result)
      if (mode === 'commit') {
        setDone(t('import.done'))
        onCommitted()
      }
    } catch (err) {
      setError(errorMessage(err, t, 'errors.import'))
    } finally {
      setBusy(false)
    }
  }

  const spReady = !!sp?.configured && !!sp.signed_in
  const canAct = source === 'local' ? !!file : spReady

  return (
    <section>
      <header className="page-header">
        <h1>{t('import.title')}</h1>
      </header>
      <p className="muted">{t('import.help')}</p>

      <div className="segmented source-switch" role="group" aria-label={t('import.source')}>
        <button className={source === 'local' ? 'active' : ''} aria-pressed={source === 'local'} onClick={() => { setSource('local'); clearReport() }}>
          {t('import.source.local')}
        </button>
        <button className={source === 'sharepoint' ? 'active' : ''} aria-pressed={source === 'sharepoint'} onClick={() => { setSource('sharepoint'); clearReport() }}>
          {t('import.source.sharepoint')}
        </button>
      </div>

      {source === 'sharepoint' && (
        <div className="card">
          {!sp && <p className="muted">{t('common.loading')}</p>}
          {sp && !sp.configured && <p className="error">{t('import.sp.notConfigured')}</p>}
          {sp?.configured && !sp.signed_in && (
            <>
              <p className="muted">{t('import.sp.notSignedIn')}</p>
              {code ? (
                <div className="device-code">
                  <p>
                    {t('import.sp.openLink')}{' '}
                    <a href={code.verification_uri} target="_blank" rel="noreferrer">
                      {code.verification_uri}
                    </a>
                  </p>
                  <p>
                    {t('import.sp.enterCode')} <strong className="code">{code.user_code}</strong>
                  </p>
                  {sp.pending && <p className="muted">{t('import.sp.waiting')}</p>}
                </div>
              ) : null}
              <button className="primary" onClick={signIn} disabled={busy || !!sp.pending}>
                {t('import.sp.signIn')}
              </button>
            </>
          )}
          {spReady && (
            <div className="sp-row">
              <p className="notice">{t('import.sp.signedInAs', { account: sp?.account ?? '' })}</p>
              <button onClick={signOut} disabled={busy}>
                {t('import.sp.signOut')}
              </button>
            </div>
          )}
          {sp?.error && !sp.pending && <p className="error">{sp.error}</p>}

          {sp?.configured && (
            <div className="sp-link">
              <label>
                {t('import.sp.link')}
                <div className="sp-row">
                  <input
                    value={linkInput}
                    onChange={(e) => setLinkInput(e.target.value)}
                    placeholder="https://…sharepoint.com/…"
                  />
                  <button onClick={saveLink} disabled={busy || !linkInput.trim() || linkInput.trim() === sp.share_url}>
                    {t('import.sp.saveLink')}
                  </button>
                </div>
              </label>
              {linkNotice && <p className="notice">{linkNotice}</p>}
            </div>
          )}
        </div>
      )}

      <div className="card import-controls">
        {source === 'local' && (
          <input
            type="file"
            accept=".xlsx,.xlsm"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null)
              setReport(null)
            }}
          />
        )}
        <button disabled={!canAct || busy} onClick={() => run('dry-run')}>
          {t('import.analyse')}
        </button>
        <button disabled={!canAct || busy || !report || report.committed} onClick={() => run('commit')}>
          {t('import.import')}
        </button>
      </div>

      {busy && <p className="muted">{t('common.processing')}</p>}
      {error && <p className="error">{error}</p>}
      {error && source === 'sharepoint' && (
        <div className="warning" role="alert">
          <h2>{t('import.alt.title')}</h2>
          <ol>
            <li>{t('import.alt.step1')}</li>
            <li>{t('import.alt.step2')}</li>
            <li>{t('import.alt.step3')}</li>
          </ol>
        </div>
      )}
      {done && <p className="notice">{done}</p>}

      <div className="card danger-zone">
        <h2>{t('clear.title')}</h2>
        {!clearOpen ? (
          <button className="danger" onClick={() => setClearOpen(true)} disabled={busy || clearing}>
            {t('clear.title')}
          </button>
        ) : (
          <div className="clear-panel" role="alertdialog" aria-labelledby="clear-warning">
            <p id="clear-warning" className="clear-warning">
              ⚠ {t('clear.warning')}
            </p>
            <label>
              {t('clear.hint', { word: t('clear.word') })}
              <input value={clearText} onChange={(e) => setClearText(e.target.value)} autoFocus />
            </label>
            <div className="sp-row">
              <button className="danger" onClick={clearData} disabled={clearing || clearText.trim().toUpperCase() !== t('clear.word')}>
                {t('clear.confirmButton')}
              </button>
              <button
                onClick={() => {
                  setClearOpen(false)
                  setClearText('')
                }}
                disabled={clearing}
              >
                {t('form.cancel')}
              </button>
            </div>
          </div>
        )}
      </div>

      {report && (
        <div className="card">
          <h2>{report.committed ? t('import.resultTitle') : t('import.analysisTitle')}</h2>
          <dl className="facts">
            <dt>{t('import.sheet')}</dt>
            <dd>{report.sheet}</dd>
            {report.source && (
              <>
                <dt>{t('import.source.label')}</dt>
                <dd>{report.source}</dd>
              </>
            )}
            <dt>{t('import.rows')}</dt>
            <dd>{report.rows}</dd>
            <dt>{t('import.newItems')}</dt>
            <dd>{report.new_items}</dd>
            <dt>{t('import.updatedItems')}</dt>
            <dd>{report.updated_items}</dd>
            <dt>{t('import.adjusted')}</dt>
            <dd>{report.adjusted_stock}</dd>
          </dl>
          {report.issues.length > 0 && (
            <>
              <h2>{t('import.issuesTitle')}</h2>
              <ul>
                {report.issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}
