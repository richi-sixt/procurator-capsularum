import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Config, ConfigResponse, Learning, ProbeResult } from '../types'
import { useT } from '../i18n'

type Props = { onClose: () => void }

const lines = (xs: string[]) => xs.join('\n')
const fromLines = (s: string) => s.split(/[\n,]/).map((x) => x.trim()).filter(Boolean)

export default function SettingsDialog({ onClose }: Props) {
  const t = useT()
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
          <h2>{t('Einstellungen')}</h2>{error ? <p className="error">{error}</p> : <p className="muted">{t('Lädt …')}</p>}
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
    if (!window.confirm(t('Alles löschen, was aus deinen Entscheidungen gemerkt wurde?'))) return
    try { await api.clearLearning(); setLearning(await api.learning()) } catch (e) { setError((e as Error).message) }
  }
  const resetLists = () => {
    setKeywords(lines(info.defaults.privacy.sensitive_keywords))
    setExtensions(lines(info.defaults.privacy.sensitive_extensions)); setSaved(false)
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog wide" role="dialog" aria-label={t('Einstellungen')} onClick={(e) => e.stopPropagation()}>
        <h2>{t('Einstellungen')}</h2>
        {info.warning && <p className="error">{info.warning}</p>}

        <h3>{t('KI-Modell')}</h3>
        <div className="field">
          <label htmlFor="s-provider">{t('Anbieter')}</label>
          <select id="s-provider" value={cfg.ai.provider} onChange={(e) => setAi({ provider: e.target.value as Config['ai']['provider'] })}>
            <option value="ollama">{t('Ollama (lokal, Standard)')}</option>
            <option value="claude">{t('Claude (Cloud)')}</option>
          </select>
        </div>
        {!cloud ? (
          <>
            <div className="field"><label htmlFor="s-om">{t('Modell')}</label>
              <input id="s-om" value={cfg.ai.ollama_model} spellCheck={false} onChange={(e) => setAi({ ollama_model: e.target.value })} /></div>
            <div className="field"><label htmlFor="s-oh">{t('Adresse (nur lokal)')}</label>
              <input id="s-oh" value={cfg.ai.ollama_host} spellCheck={false} onChange={(e) => setAi({ ollama_host: e.target.value })} /></div>
          </>
        ) : (
          <>
            <p className="error" role="note">
              {t('Cloud: Beim Analysieren würden Dateinamen und Metadaten an Anthropic gesendet. Sensible Dateien werden auch dann nie gesendet.')}
            </p>
            <div className="field"><label htmlFor="s-cm">{t('Modell')}</label>
              <input id="s-cm" value={cfg.ai.claude_model} spellCheck={false} onChange={(e) => setAi({ claude_model: e.target.value })} /></div>
            <div className="field"><label htmlFor="s-ke">{t('Name der Umgebungsvariable mit dem Schlüssel')}</label>
              <input id="s-ke" value={cfg.ai.api_key_env} spellCheck={false} onChange={(e) => setAi({ api_key_env: e.target.value })} />
              <small className="muted">{t('Der Schlüssel selbst wird nie gespeichert.')} {t('Status')}: {info.apiKeyPresent ? t('Variable ist gesetzt') : t('Variable ist nicht gesetzt')}</small></div>
          </>
        )}
        <div className="presets">
          <button onClick={() => void test()}>{t('Verbindung testen')}</button>
          {probe && <span className={probe.ok ? 'notice' : 'error'} role="status">{probe.message}</span>}
        </div>
        {probe && probe.models.length > 0 && <small className="muted">{t('Geladene Modelle')}: {probe.models.join(', ')}</small>}

        <h3>{t('Datenschutzstufe')}</h3>
        <div className="field">
          {Object.entries(info.privacyLevels).map(([lvl, text]) => (
            <label key={lvl} className="check">
              <input type="radio" name="level" checked={cfg.ai.privacy_level === Number(lvl)} onChange={() => setAi({ privacy_level: Number(lvl) })} />
              <span><strong>{t('Stufe {n}', { n: lvl })}:</strong> {text}</span>
            </label>
          ))}
          <small className="muted">
            {cloud
              ? t('Bei Cloud braucht jeder Lauf eine ausdrückliche Freigabe vor dem Start.')
              : t('Beim lokalen Modell verlassen die Daten den Rechner nicht, eine Freigabe vor jedem Lauf entfällt.')}
          </small>
        </div>

        <h3>{t('Aus Entscheidungen lernen')}</h3>
        <label className="check">
          <input type="checkbox" checked={cfg.ai.learn} onChange={(e) => setAi({ learn: e.target.checked })} />
          <span>{t('Angenommene, abgelehnte und korrigierte Vorschläge merken und dem Modell als Beispiele mitgeben')}
            <small className="muted"> ({t('Standard: an. Gemerkt wird nur auf diesem Rechner, sensible Dateien nie.')}
              {cloud ? ' ' + t('Bei Cloud gehen Beispiele erst ab Datenschutzstufe 1 mit und stehen in der Freigabe.') : ''})</small></span>
        </label>
        {learning && (
          <p className="muted small">
            {t('Gemerkt: {accepted} angenommen, {edited} korrigiert, {rejected} abgelehnt.', learning.stats)}{' '}
            {learning.stats.total > 0 && <button className="link" onClick={() => void clearLearning()}>{t('Alles löschen')}</button>}
          </p>
        )}

        <h3>{t('Sensible Dateien')}</h3>
        <p className="muted small">
          {t('Dateien mit diesen Wörtern am Wortanfang (Name oder Ordnername) oder Endungen werden markiert und nie an ein Modell gesendet. Ein Eintrag pro Zeile.')}
        </p>
        <div className="field"><label htmlFor="s-kw">{t('Schlüsselwörter')}</label>
          <textarea id="s-kw" rows={6} value={keywords} spellCheck={false} onChange={(e) => { setKeywords(e.target.value); setSaved(false) }} /></div>
        <div className="field"><label htmlFor="s-ex">{t('Endungen')}</label>
          <textarea id="s-ex" rows={2} value={extensions} spellCheck={false} onChange={(e) => { setExtensions(e.target.value); setSaved(false) }} /></div>
        <label className="check">
          <input type="checkbox" disabled={cloud}
            checked={!cloud && cfg.privacy.allow_sensitive_local}
            onChange={(e) => { setCfg({ ...cfg, privacy: { ...cfg.privacy, allow_sensitive_local: e.target.checked } }); setSaved(false) }} />
          <span>{t('Sensible Dateien auch an das lokale Modell senden')}
            <small className="muted"> {cloud ? t('(bei Cloud nie möglich)') : t('(Standard: aus. Die Daten bleiben auf dem Rechner.)')}</small></span>
        </label>
        <button className="link" onClick={resetLists}>{t('Auf Standard zurücksetzen')}</button>

        {error && <p className="error" role="alert">{error}</p>}
        {saved && <p className="notice" role="status">{t('Gespeichert.')}</p>}
        <div className="dialog-actions">
          <span className="muted small">{info.path}</span>
          <button onClick={onClose}>{t('Schliessen')}</button>
          <button className="primary" onClick={() => void save()}>{t('Speichern')}</button>
        </div>
      </div>
    </div>
  )
}
