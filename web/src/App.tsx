import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type PlanInput } from './api'
import AboutDialog from './components/AboutDialog'
import FolderPicker from './components/FolderPicker'
import HelpDialog from './components/HelpDialog'
import HistoryPanel from './components/HistoryPanel'
import OperationForm, { defaults, missingRequired } from './components/OperationForm'
import PreviewTable from './components/PreviewTable'
import { useI18n } from './i18n'
import { isImage } from './thumbs'
import SendDialog from './components/SendDialog'
import SettingsDialog from './components/SettingsDialog'
import type { Job, OperationSpec, Params, PlanResponse, Preset, SendPreview } from './types'

const human = (n: number) => {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${i === 0 ? n.toFixed(0) : n.toFixed(1)} ${units[i]}`
}

export default function App() {
  const { t, tx, lang, prefs, setPrefs } = useI18n()
  const [specs, setSpecs] = useState<OperationSpec[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [paths, setPaths] = useState<string[]>([])
  const [pathText, setPathText] = useState('')
  const [recursive, setRecursive] = useState(false)
  const [forceUnique, setForceUnique] = useState(false)
  const [opName, setOpName] = useState('replace')
  const [params, setParams] = useState<Params>({})
  const [order, setOrder] = useState<string[] | null>(null)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [listing, setListing] = useState(false) // nur Dateiliste, noch keine Aktion
  const [disabled, setDisabled] = useState<Set<string>>(new Set())
  const [showSkipped, setShowSkipped] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [picker, setPicker] = useState(false)
  const [history, setHistory] = useState(false)
  const [settings, setSettings] = useState(false)
  const [aboutOpen, setAboutOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [sendInfo, setSendInfo] = useState<SendPreview | null>(null) // Bestätigung vor dem Senden
  const [job, setJob] = useState<Job | null>(null) // laufender Auftrag
  const [jobKind, setJobKind] = useState<'apply' | 'analyze'>('apply')
  const [refresh, setRefresh] = useState(0)
  const requestId = useRef(0)

  const spec = specs.find((s) => s.name === opName)

  useEffect(() => {
    api.operations().then((ops) => {
      setSpecs(ops)
      setParams((cur) => (Object.keys(cur).length ? cur : defaults(ops.find((o) => o.name === 'replace')!)))
    }).catch((e: Error) => setError(t('Server nicht erreichbar: {error}', { error: e.message })))
    void api.presets().then(setPresets).catch(() => undefined)
  }, [lang]) // eslint-disable-line react-hooks/exhaustive-deps

  const input: PlanInput = useMemo(
    () => ({ paths, recursive, operation: opName, params, force_unique: forceUnique, order }),
    [paths, recursive, opName, params, forceUnique, order],
  )

  // Vorschau neu berechnen (entprellt); veraltete Antworten werden verworfen.
  useEffect(() => {
    if (!spec || paths.length === 0) { setPlan(null); setListing(false); return }
    const missing = missingRequired(spec, params)
    const id = ++requestId.current
    const ctl = new AbortController()
    if (missing.length) {
      // Pflichtfeld fehlt: nur die Dateien des Ordners zeigen
      api.scan(paths, recursive, ctl.signal).then((files) => {
        if (id !== requestId.current) return
        const changes = files.map((f) => ({ ...f, dst: null, dstName: null, status: 'skip' as const, reason: '' }))
        setPlan({ operation: opName, counts: { ok: 0, skip: changes.length, conflict: 0, error: 0 }, changes })
        setListing(true); setError('')
      }).catch((e: Error) => {
        if (e.name !== 'AbortError' && id === requestId.current) { setPlan(null); setError(e.message) }
      })
      return () => ctl.abort()
    }
    const t = setTimeout(() => {
      api.plan(input, ctl.signal).then((p) => {
        if (id !== requestId.current) return
        setPlan(p); setListing(false); setError('')
      }).catch((e: Error) => {
        if (e.name !== 'AbortError' && id === requestId.current) { setPlan(null); setError(e.message) }
      })
    }, 250)
    return () => { clearTimeout(t); ctl.abort() }
  }, [input, spec, params, paths, recursive, opName, refresh, lang])

  const missing = spec ? missingRequired(spec, params) : []
  const sortCustom = opName === 'sequence' && params.sort === 'custom'
  const runnable = plan ? plan.changes.filter((c) => c.status === 'ok' && !disabled.has(c.src)).length : 0

  const addPath = useCallback((p: string) => {
    const clean = p.trim()
    if (!clean) return
    setPaths((cur) => (cur.includes(clean) ? cur : [...cur, clean]))
    setOrder(null); setPathText(''); setNotice('')
  }, [])

  const chooseOp = (name: string) => {
    const s = specs.find((o) => o.name === name)!
    setOpName(name); setParams(defaults(s)); setOrder(null); setNotice('')
  }

  const busy = job?.state === 'running'

  // Auftrag verfolgen, bis er fertig ist (Fortschritt in `job`)
  const track = async (first: Job) => {
    let current = first
    setJob(current)
    while (current.state === 'running') {
      await new Promise((r) => setTimeout(r, 400))
      current = await api.job(current.id)
      setJob(current)
    }
    return current
  }

  const apply = async () => {
    setNotice(''); setError(''); setJobKind('apply')
    try {
      const current = await track(await api.apply(input, [...disabled]))
      const verb = spec?.kind === 'convert' ? t('konvertiert') : (opName === 'move' || opName === 'duplicates') ? t('verschoben') : opName === 'ai_organize' ? t('angewendet') : t('umbenannt')
      if (current.state === 'error') setError(current.error)
      else setNotice(
        `${current.ok} ${verb}${current.state === 'cancelled' ? ' ' + t('(abgebrochen)') : ''}` +
        (current.failed.length ? ', ' + t('{n} fehlgeschlagen ({details})', { n: current.failed.length, details: current.failed.map((f) => `${f.src}: ${f.error}`).join('; ') }) : '') +
        '.' + (current.batchId ? ' ' + t('Lauf #{id}, im Verlauf rückgängig zu machen.', { id: current.batchId }) : ''),
      )
      setDisabled(new Set()); setRefresh((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    } finally { setJob(null) }
  }

  // Langsamer Vorbereitungsschritt (zum Beispiel Dateien für die Dublettensuche lesen)
  const analyze = async (confirmCloud = false) => {
    setNotice(''); setError(''); setJobKind('analyze'); setSendInfo(null)
    try {
      const current = await track(await api.analyze({ ...input, confirm_cloud: confirmCloud }))
      if (current.state === 'error') setError(current.error)
      else setNotice(current.state === 'cancelled'
        ? t('Analyse abgebrochen. Was schon gelesen ist, bleibt gespeichert, du kannst später weitermachen.')
        : t('Analyse fertig.'))
      if (params.reanalyze) setParams((cur) => ({ ...cur, reanalyze: false })) // «Neu berechnen» gilt nur einmal
      setRefresh((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    } finally { setJob(null) }
  }

  // Bei Cloud zuerst zeigen, was gesendet würde. Lokal geht es direkt los.
  const startAnalysis = async () => {
    if (plan?.info?.requiresConfirmation) {
      try { setSendInfo(await api.analyzePreview(input)) } catch (e) { setError((e as Error).message) }
    } else {
      await analyze(false)
    }
  }

  const editTarget = async (src: string, text: string) => {
    setError('')
    try {
      await api.editProposal(input, src, text)
      setRefresh((n) => n + 1)
    } catch (e) { setError((e as Error).message) }
  }

  const cancel = () => { if (job) void api.cancelJob(job.id) }

  const savePreset = async () => {
    const name = window.prompt(t('Name für diese Einstellung:'))?.trim()
    if (!name) return
    await api.savePreset({ name, operation: opName, params })
    setPresets(await api.presets())
  }

  const loadPreset = (name: string) => {
    const p = presets.find((x) => x.name === name)
    if (!p) return
    const s = specs.find((o) => o.name === p.operation)
    if (!s) return
    setOpName(p.operation); setParams({ ...defaults(s), ...p.params }); setOrder(null)
  }

  const deletePreset = async (name: string) => {
    await api.deletePreset(name)
    setPresets(await api.presets())
  }

  const groups = [...new Set(specs.map((s) => s.group))]
  const counts = plan?.counts

  return (
    <div className="app">
      <header>
        <h1>
          <img src="/favicon.svg" alt="" className="logo" />
          Procurator Capsularum
        </h1>
        <div className="header-actions">
          <button onClick={() => setSettings(true)}>{t('Einstellungen')}</button>
          <button onClick={() => setHistory(true)}>{t('Verlauf')}</button>
          <button onClick={() => setHelpOpen(true)}>{t('Hilfe')}</button>
          <button className="icon-btn" aria-label={t('Darstellung wechseln')}
            title={`${t('Darstellung')}: ${prefs.theme === 'auto' ? t('System') : prefs.theme === 'light' ? t('Hell') : t('Dunkel')}`}
            onClick={() => setPrefs({ theme: prefs.theme === 'auto' ? 'light' : prefs.theme === 'light' ? 'dark' : 'auto' })}>
            {prefs.theme === 'auto' ? '◐' : prefs.theme === 'light' ? '☀' : '☾'}
          </button>
          <select className="lang-select" aria-label={t('Sprache')} value={prefs.language}
            onChange={(e) => setPrefs({ language: e.target.value as 'auto' | 'de' | 'en' })}>
            <option value="auto">{t('Auto')}</option>
            <option value="de">Deutsch</option>
            <option value="en">English</option>
          </select>
        </div>
      </header>

      <div className="layout">
        <section className="panel" aria-label={t('Einstellungen')}>
          <h2>{t('1. Ordner')}</h2>
          <div className="path-add">
            <input value={pathText} placeholder={t('/Pfad/zum/Ordner')} spellCheck={false}
              onChange={(e) => setPathText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addPath(pathText)} />
            <button onClick={() => addPath(pathText)} disabled={!pathText.trim()}>{t('Hinzufügen')}</button>
            <button onClick={() => setPicker(true)}>{t('Wählen …')}</button>
          </div>
          <ul className="chips">
            {paths.map((p) => (
              <li key={p}>{p}<button className="link" aria-label={t('{path} entfernen', { path: p })}
                onClick={() => { setPaths(paths.filter((x) => x !== p)); setOrder(null) }}>✕</button></li>
            ))}
          </ul>
          <label className="check"><input type="checkbox" checked={recursive}
            onChange={(e) => { setRecursive(e.target.checked); setOrder(null) }} />{t('Unterordner einbeziehen')}</label>

          <h2>{t('2. Aktion')}</h2>
          <select aria-label={t('Aktion')} value={opName} onChange={(e) => chooseOp(e.target.value)}>
            {groups.map((g) => (
              <optgroup key={g} label={g}>
                {specs.filter((s) => s.group === g).map((s) => <option key={s.name} value={s.name}>{s.label}</option>)}
              </optgroup>
            ))}
          </select>
          {spec && <OperationForm spec={spec} params={params} onChange={setParams} />}
          <label className="check"><input type="checkbox" checked={forceUnique}
            onChange={(e) => setForceUnique(e.target.checked)} />{t('Bei Kollision Nummer anhängen')}</label>

          <h2>{t('Gespeichert')}</h2>
          <div className="presets">
            <select aria-label={t('Gespeicherte Einstellung')} value="" onChange={(e) => loadPreset(e.target.value)}>
              <option value="">{t('Laden …')}</option>
              {presets.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
            </select>
            <button onClick={() => void savePreset()} disabled={!spec || missing.length > 0}>{t('Speichern')}</button>
          </div>
          {presets.length > 0 && (
            <ul className="chips">
              {presets.map((p) => (
                <li key={p.name}>{p.name}<button className="link" aria-label={t('{name} löschen', { name: p.name })}
                  onClick={() => void deletePreset(p.name)}>✕</button></li>
              ))}
            </ul>
          )}
        </section>

        <main className="panel" aria-label={t('Vorschau')}>
          <div className="main-head">
            <h2>{t('3. Vorschau')}</h2>
            {counts && !listing && (
              <span className="muted">
                {t('{ok} bereit · {skip} übersprungen · {conflict} Konflikte · {error} Fehler', counts)}
                {plan?.sensitiveCount ? ` · 🔒 ${t('{n} sensibel', { n: plan.sensitiveCount })}` : ''}
                {typeof plan?.info?.duplicates === 'number' ? ` · ${t(plan.info.duplicates === 1 ? '{n} Kopie' : '{n} Kopien', { n: plan.info.duplicates })} ${t('in')} ${t(plan.info.groups === 1 ? '{n} Gruppe' : '{n} Gruppen', { n: plan.info.groups })} (${human(Number(plan.info.bytes))})` : ''}
              </span>
            )}
            {plan?.changes.some((c) => isImage(c.srcName)) && (
              <label className="check push"><input type="checkbox" checked={prefs.thumbs}
                onChange={(e) => setPrefs({ thumbs: e.target.checked })} />{t('Vorschaubilder')}</label>
            )}
            <label className="check"><input type="checkbox" checked={showSkipped}
              onChange={(e) => setShowSkipped(e.target.checked)} />{t('Übersprungene zeigen')}</label>
          </div>

          {error && <p className="error" role="alert">{error}</p>}
          {notice && <p className="notice" role="status">{notice}</p>}
          {plan?.needsAnalysis && !listing && (
            busy && job && jobKind === 'analyze' ? (
              <div className="banner" role="status">
                <span>{t('Analyse läuft …')}</span>
                <progress max={Math.max(job.total, 1)} value={job.done} aria-label={t('Fortschritt der Analyse')} />
                <span className="muted small">{job.done}/{job.total} {job.current}</span>
                <button onClick={cancel}>{t('Abbrechen')}</button>
              </div>
            ) : Number(plan.info?.pendingFiles ?? 0) > 0 ? (
              <div className="banner">
                <span>
                  {typeof plan.info?.analysisHint === 'string' ? plan.info.analysisHint : (
                    <>
                      {tx('Für die Suche müssen noch {n} Dateien gelesen werden (etwa {size}). Schon bekannte Dateien werden nicht erneut gelesen.', {
                        n: <strong>{Number(plan.info?.pendingFiles)}</strong>, size: human(Number(plan.info?.pendingBytes ?? 0)),
                      })}
                    </>
                  )}
                </span>
                <button className="primary" onClick={() => void startAnalysis()} disabled={busy}>{t('Analysieren')}</button>
              </div>
            ) : null
          )}
          {paths.length === 0 && <p className="empty">{t('Wähle links einen Ordner, dann eine Aktion.')}</p>}
          {listing && plan && plan.changes.length > 0 && <p className="muted small">{t('{n} Dateien. Fülle links die Aktion aus ({missing}), dann erscheint die Vorschau der neuen Namen.', { n: plan.changes.length, missing: missing.join(', ') })}</p>}
          {plan && plan.changes.length === 0 && <p className="empty">{t('Keine Dateien gefunden.')}</p>}
          {plan && !listing && plan.changes.length > 0 && counts && counts.ok + counts.conflict + counts.error === 0 && !showSkipped && !Number(plan.info?.pendingFiles ?? 0) && (
            <p className="empty">{t('Nichts zu tun: alle {n} Dateien werden übersprungen. «Übersprungene zeigen» nennt die Gründe.', { n: counts.skip })}</p>
          )}

          {plan && plan.changes.length > 0 && (
            <>
              {sortCustom && <p className="muted small">{t('Zeilen per Ziehen umsortieren: bestimmt die Nummerierung.')}</p>}
              <PreviewTable changes={plan.changes} thumbs={prefs.thumbs} showSkipped={showSkipped || listing} listing={listing}
                  showFolder={recursive || paths.length > 1}
                  disabled={disabled}
                  onToggle={(s) => setDisabled((d) => { const n = new Set(d); if (n.has(s)) n.delete(s); else n.add(s); return n })}
                  onToggleAll={(on) => setDisabled(on ? new Set() : new Set(plan.changes.filter((c) => c.status === 'ok').map((c) => c.src)))}
                  draggable={sortCustom} onReorder={setOrder} onEdit={opName === 'ai_organize' ? editTarget : undefined} />
              {!listing && <div className="actionbar">
                <span className="muted">{t('{n} von {total} ausgewählt', { n: runnable, total: counts?.ok ?? 0 })}</span>
                {busy && job && jobKind === 'apply' ? (
                  <>
                    <progress max={Math.max(job.total, 1)} value={job.done} aria-label={t('Fortschritt')} />
                    <span className="muted small">{job.done}/{job.total} {job.current}</span>
                    <button onClick={cancel}>{t('Abbrechen')}</button>
                  </>
                ) : (
                  <button className="primary" disabled={runnable === 0 || busy} onClick={() => void apply()}>
                    {t('{n} Dateien {verb}', { n: runnable, verb: spec?.kind === 'convert' ? t('konvertieren') : (opName === 'move' || opName === 'duplicates' || opName === 'sort_template') ? t('verschieben') : opName === 'ai_organize' ? t('anwenden') : t('umbenennen') })}
                  </button>
                )}
              </div>}
            </>
          )}
        </main>
      </div>

      <footer className="legal">
        Procurator Capsularum · © 2026 Rüchan Sixt · {t('Lizenz')}: AGPL-3.0-or-later · {t('Ohne jede Gewährleistung')} ·{' '}
        <a href="https://github.com/richi-sixt/procurator-capsularum" target="_blank" rel="noreferrer">{t('Quellcode')}</a> ·{' '}
        <button className="link" onClick={() => setAboutOpen(true)}>{t('Über das Programm')}</button>
      </footer>

      {sendInfo && <SendDialog info={sendInfo} onCancel={() => setSendInfo(null)} onConfirm={() => void analyze(true)} />}
      {picker && <FolderPicker start={paths[paths.length - 1]} onClose={() => setPicker(false)}
        onPick={(p) => { addPath(p); setPicker(false) }} />}
      {aboutOpen && <AboutDialog onClose={() => setAboutOpen(false)} />}
      {helpOpen && <HelpDialog onClose={() => setHelpOpen(false)} />}
      {settings && <SettingsDialog onClose={() => { setSettings(false); setRefresh((n) => n + 1) }} />}
      {history && <HistoryPanel onClose={() => setHistory(false)} onChanged={() => setRefresh((n) => n + 1)} />}
    </div>
  )
}
