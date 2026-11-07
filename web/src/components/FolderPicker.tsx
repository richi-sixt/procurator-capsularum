import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Browse } from '../types'
import { useT } from '../i18n'

type Props = { start?: string; onPick: (path: string) => void; onClose: () => void }

export default function FolderPicker({ start = '', onPick, onClose }: Props) {
  const t = useT()
  const [data, setData] = useState<Browse | null>(null)
  const [error, setError] = useState('')

  const open = (path: string) =>
    api.browse(path).then((d) => { setData(d); setError('') }).catch((e: Error) => setError(e.message))

  useEffect(() => { void open(start) }, [start])

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-label={t('Ordner wählen')} onClick={(e) => e.stopPropagation()}>
        <h2>{t('Ordner wählen')}</h2>
        <div className="crumb">{data?.path ?? '…'}</div>
        {error && <p className="error">{error}</p>}
        <ul className="dirlist">
          {data?.parent && (
            <li><button className="link" onClick={() => open(data.parent!)}>↑ {t('Übergeordneter Ordner')}</button></li>
          )}
          {data?.dirs.map((d) => (
            <li key={d}>
              <button className="link" onClick={() => open(`${data.path.replace(/\/$/, '')}/${d}`)}>📁 {d}</button>
            </li>
          ))}
          {data && data.dirs.length === 0 && <li className="muted">{t('Keine Unterordner')}</li>}
        </ul>
        <div className="dialog-actions">
          <span className="muted">{data ? t('{n} Dateien hier', { n: data.fileCount }) : ''}</span>
          <button onClick={onClose}>{t('Abbrechen')}</button>
          <button className="primary" disabled={!data} onClick={() => data && onPick(data.path)}>
            {t('Diesen Ordner wählen')}
          </button>
        </div>
      </div>
    </div>
  )
}
