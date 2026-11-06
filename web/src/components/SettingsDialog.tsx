import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Config, ConfigResponse, Learning, ProbeResult } from '../types'

type Props = { onClose: () => void }

const lines = (xs: string[]) => xs.join('\n')
const fromLines = (s: string) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean)

export default function SettingsDialog({ onClose }: Props) {
  const [info, setInfo] = useState<ConfigResponse | null>(null)
  const [cfg, setCfg] = useState<Config | null>(null)
  const [keywords, setKeywords] = useState('')
  const [extensions, setExtensions] = useState('')
  const [probe, setProbe] = useState<ProbeResult | null>(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [learning, setLearning] = useState<Learning | null>(null)

  useEffect(() => {
    api.config().then((r) => {
      setInfo(r); setCfg(r.config)
      setKeywords(lines(r.config.privacy.sensitive_keywords))
      setExtensions(lines(r.config.privacy.sensitive_extensions))
    }).catch((e: Error) => setError(e.message))
    api.learning().then(setLearning).catch(() => setLearning(null))
  }, [])

  if (!cfg || !info) {
    return (
      <div className="overlay" onClick={onClose}>
        <div className="dialog" onClick={(e) => e.stopPropagation()}>
          <h2>Einstellungen</h2>{error ? <p className="error">{error}</p> : <p className="muted">Lädt …</p>}
        </div>
      </div>
    )
  }

  const current = (): Config => ({
    ai: cfg.ai,
    privacy: {
      sensitive_keywords: fromLines(keywords), sensitive_extensions: fromLines(extensions),
      allow_sensitive_local: cfg.privacy.allow_sensitive_local,
    },
  })
  const setAi = (patch: Partial<Config['ai']>) => { setCfg({ ...cfg, ai: { ...cfg.ai, ...patch } }); setSaved(false); setProbe(null) }
  const cloud = cfg.ai.provider === 'claude'

  const test = async () => {
    setError(''); setProbe(null)
    try { setProbe(await api.testConfig(current())) } catch (e) { setError((e as Error).message) }
  }
  const save = async () => {
    setError('')
    try {
      const r = await api.saveConfig(current())
      setInfo(r); setCfg(r.config); setSaved(true)
      setKeywords(lines(r.config.privacy.sensitive_keywords))
      setExtensions(lines(r.config.privacy.sensitive_extensions))
    } catch (e) { setError((e as Error).message) }
  }
  const clearLearning = async () => {
    if (!window.confirm('Alles löschen, was aus deinen Entscheidungen gemerkt wurde?')) return
    try { await api.clearLearning(); setLearning(await api.learning()) } catch (e) { setError((e as Error).message) }
  }
  const resetLists = () => {
    setKeywords(lines(info.defaults.privacy.sensitive_keywords))
    setExtensions(lines(info.defaults.privacy.sensitive_extensions)); setSaved(false)
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog wide" role="dialog" aria-label="Einstellungen" onClick={(e) => e.stopPropagation()}>
        <h2>Einstellungen</h2>
        {info.warning && <p className="error">{info.warning}</p>}

        <h3>KI-Modell</h3>
        <div className="field">
          <label htmlFor="s-provider">Anbieter</label>
          <select id="s-provider" value={cfg.ai.provider} onChange={(e) => setAi({ provider: e.target.value as Config['ai']['provider'] })}>
            <option value="ollama">Ollama (lokal, Standard)</option>
            <option value="claude">Claude (Cloud)</option>
          </select>
        </div>
        {!cloud ? (
          <>
            <div className="field"><label htmlFor="s-om">Modell</label>
              <input id="s-om" value={cfg.ai.ollama_model} spellCheck={false} onChange={(e) => setAi({ ollama_model: e.target.value })} /></div>
            <div className="field"><label htmlFor="s-oh">Adresse (nur lokal)</label>
              <input id="s-oh" value={cfg.ai.ollama_host} spellCheck={false} onChange={(e) => setAi({ ollama_host: e.target.value })} /></div>
          </>
        ) : (
          <>
            <p className="error" role="note">
              Cloud: Beim Analysieren würden Dateinamen und Metadaten an Anthropic gesendet. Sensible Dateien
              werden auch dann nie gesendet.
            </p>
            <div className="field"><label htmlFor="s-cm">Modell</label>
              <input id="s-cm" value={cfg.ai.claude_model} spellCheck={false} onChange={(e) => setAi({ claude_model: e.target.value })} /></div>
            <div className="field"><label htmlFor="s-ke">Name der Umgebungsvariable mit dem Schlüssel</label>
              <input id="s-ke" value={cfg.ai.api_key_env} spellCheck={false} onChange={(e) => setAi({ api_key_env: e.target.value })} />
              <small className="muted">Der Schlüssel selbst wird nie gespeichert. Status: {info.apiKeyPresent ? 'Variable ist gesetzt' : 'Variable ist nicht gesetzt'}</small></div>
          </>
        )}
        <div className="presets">
          <button onClick={() => void test()}>Verbindung testen</button>
          {probe && <span className={probe.ok ? 'notice' : 'error'} role="status">{probe.message}</span>}
        </div>
        {probe && probe.models.length > 0 && <small className="muted">Geladene Modelle: {probe.models.join(', ')}</small>}

        <h3>Datenschutzstufe</h3>
        <div className="field">
          {Object.entries(info.privacyLevels).map(([lvl, text]) => (
            <label key={lvl} className="check">
              <input type="radio" name="level" checked={cfg.ai.privacy_level === Number(lvl)} onChange={() => setAi({ privacy_level: Number(lvl) })} />
              <span><strong>Stufe {lvl}:</strong> {text}</span>
            </label>
          ))}
          <small className="muted">
            {cloud
              ? 'Bei Cloud braucht jeder Lauf eine ausdrückliche Freigabe vor dem Start.'
              : 'Beim lokalen Modell verlassen die Daten den Rechner nicht, eine Freigabe vor jedem Lauf entfällt.'}
          </small>
        </div>

        <h3>Aus Entscheidungen lernen</h3>
        <label className="check">
          <input type="checkbox" checked={cfg.ai.learn} onChange={(e) => setAi({ learn: e.target.checked })} />
          <span>Angenommene, abgelehnte und korrigierte Vorschläge merken und dem Modell als Beispiele mitgeben
            <small className="muted"> (Standard: an. Gemerkt wird nur auf diesem Rechner, sensible Dateien nie.
              {cloud ? ' Bei Cloud gehen Beispiele erst ab Datenschutzstufe 1 mit und stehen in der Freigabe.' : ''})</small></span>
        </label>
        {learning && (
          <p className="muted small">
            Gemerkt: {learning.stats.accepted} angenommen, {learning.stats.edited} korrigiert, {learning.stats.rejected} abgelehnt.{' '}
            {learning.stats.total > 0 && <button className="link" onClick={() => void clearLearning()}>Alles löschen</button>}
          </p>
        )}

        <h3>Sensible Dateien</h3>
        <p className="muted small">
          Dateien mit diesen Wörtern am Wortanfang (Name oder Ordnername) oder Endungen werden markiert
          und nie an ein Modell gesendet. Ein Eintrag pro Zeile.
        </p>
        <div className="field"><label htmlFor="s-kw">Schlüsselwörter</label>
          <textarea id="s-kw" rows={6} value={keywords} spellCheck={false} onChange={(e) => { setKeywords(e.target.value); setSaved(false) }} /></div>
        <div className="field"><label htmlFor="s-ex">Endungen</label>
          <textarea id="s-ex" rows={2} value={extensions} spellCheck={false} onChange={(e) => { setExtensions(e.target.value); setSaved(false) }} /></div>
        <label className="check">
          <input type="checkbox" disabled={cloud}
            checked={!cloud && cfg.privacy.allow_sensitive_local}
            onChange={(e) => { setCfg({ ...cfg, privacy: { ...cfg.privacy, allow_sensitive_local: e.target.checked } }); setSaved(false) }} />
          <span>Sensible Dateien auch an das lokale Modell senden
            <small className="muted"> {cloud ? '(bei Cloud nie möglich)' : '(Standard: aus. Die Daten bleiben auf dem Rechner.)'}</small></span>
        </label>
        <button className="link" onClick={resetLists}>Auf Standard zurücksetzen</button>

        {error && <p className="error" role="alert">{error}</p>}
        {saved && <p className="notice" role="status">Gespeichert.</p>}
        <div className="dialog-actions">
          <span className="muted small">{info.path}</span>
          <button onClick={onClose}>Schliessen</button>
          <button className="primary" onClick={() => void save()}>Speichern</button>
        </div>
      </div>
    </div>
  )
}
