import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Browse } from '../types'

type Props = { start?: string; onPick: (path: string) => void; onClose: () => void }

export default function FolderPicker({ start = '', onPick, onClose }: Props) {
  const [data, setData] = useState<Browse | null>(null)
  const [error, setError] = useState('')

  const open = (path: string) =>
    api.browse(path).then((d) => { setData(d); setError('') }).catch((e: Error) => setError(e.message))

  useEffect(() => { void open(start) }, [start])

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label="Ordner wählen" onClick={(e) => e.stopPropagation()}>
        <h2>Ordner wählen</h2>
        <div className="crumb">{data?.path ?? '…'}</div>
        {error && <p className="error">{error}</p>}
        <ul className="dirlist">
          {data?.parent && (
            <li><button className="link" onClick={() => open(data.parent!)}>↑ Übergeordneter Ordner</button></li>
          )}
          {data?.dirs.map((d) => (
            <li key={d}>
              <button className="link" onClick={() => open(`${data.path.replace(/\/$/, '')}/${d}`)}>📁 {d}</button>
            </li>
          ))}
          {data && data.dirs.length === 0 && <li className="muted">Keine Unterordner</li>}
        </ul>
        <div className="dialog-actions">
          <span className="muted">{data ? `${data.fileCount} Dateien hier` : ''}</span>
          <button onClick={onClose}>Abbrechen</button>
          <button className="primary" disabled={!data} onClick={() => data && onPick(data.path)}>
            Diesen Ordner wählen
          </button>
        </div>
      </div>
    </div>
  )
}
