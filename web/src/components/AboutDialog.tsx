import { useEffect, useState } from 'react'
import { api } from '../api'
import type { About, Component } from '../types'

type Props = { onClose: () => void }

const rows = (items: Component[], kind: string) =>
  items.map((c) => (
    <tr key={`${kind}-${c.name}`}>
      <td>{c.name}{c.optional && <span className="muted small"> (optional)</span>}</td>
      <td>{c.version}</td>
      <td>{c.license}</td>
      <td className="muted">{kind}</td>
    </tr>
  ))

export default function AboutDialog({ onClose }: Props) {
  const [info, setInfo] = useState<About | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.about().then(setInfo).catch((e: Error) => setError(e.message))
  }, [])

  const support = info
    ? `${info.name} ${info.version}\nPython ${info.system.python}\n${info.system.platform}`
    : ''
  const copy = async () => {
    try { await navigator.clipboard.writeText(support); setCopied(true) } catch { setCopied(false) }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog wide" role="dialog" aria-label="Über das Programm" onClick={(e) => e.stopPropagation()}>
        {error && <p className="error">{error}</p>}
        {!info && !error && <p className="muted">Lädt …</p>}
        {info && (
          <>
            <h2>{info.name}</h2>
            <p><strong>Version {info.version}</strong></p>
            <p>{info.copyright}</p>

            <h3>Lizenz</h3>
            <p>
              <a href={info.license.url} target="_blank" rel="noreferrer">{info.license.name}</a>{' '}
              ({info.license.id}). Den Quellcode findest du unter{' '}
              <a href={info.repository} target="_blank" rel="noreferrer">{info.repository}</a>.
            </p>
            <p className="muted small">{info.notice}</p>

            <h3>Ideen</h3>
            <ul>
              {info.inspiration.map((i) => (
                <li key={i.name}>
                  {i.url ? <a href={i.url} target="_blank" rel="noreferrer">{i.name}</a> : <strong>{i.name}</strong>}
                  {': '}{i.note}. Es wurde kein Code übernommen.
                </li>
              ))}
            </ul>

            <h3>Separat installierte Programme</h3>
            <ul>
              {info.external.map((e) => (
                <li key={e.name}><a href={e.url} target="_blank" rel="noreferrer">{e.name}</a>: {e.note}. Es gilt die jeweils eigene Lizenz.</li>
              ))}
            </ul>

            <details>
              <summary>Verwendete Bausteine ({info.components.python.length + info.components.frontend.length})</summary>
              <table className="preview components">
                <thead><tr><th>Baustein</th><th>Version</th><th>Lizenz</th><th>Art</th></tr></thead>
                <tbody>
                  {rows(info.components.frontend, 'Oberfläche')}
                  {rows(info.components.python, 'Python')}
                </tbody>
              </table>
            </details>

            <h3>Für Fehlermeldungen</h3>
            <pre className="sample">{support}</pre>
            <div className="dialog-actions">
              <button onClick={() => void copy()}>{copied ? 'Kopiert' : 'Kopieren'}</button>
              <button className="primary" onClick={onClose}>Schliessen</button>
            </div>
          </>
        )}
        {!info && <div className="dialog-actions"><button onClick={onClose}>Schliessen</button></div>}
      </div>
    </div>
  )
}
