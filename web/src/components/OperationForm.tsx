import { useState } from 'react'
import FolderPicker from './FolderPicker'
import type { Field, OperationSpec, Params } from '../types'
import { useT } from '../i18n'

type Props = { spec: OperationSpec; params: Params; onChange: (p: Params) => void }

export function defaults(spec: OperationSpec): Params {
  return Object.fromEntries(spec.fields.map((f) => [f.key, f.default]))
}

export function missingRequired(spec: OperationSpec, params: Params): string[] {
  return spec.fields
    .filter((f) => f.required && (params[f.key] === '' || params[f.key] == null))
    .map((f) => f.label)
}

const visible = (f: Field, params: Params) =>
  !f.showIf || Object.entries(f.showIf).every(([k, v]) => String(params[k]) === v)

export default function OperationForm({ spec, params, onChange }: Props) {
  const t = useT()
  const [pickerFor, setPickerFor] = useState<string | null>(null)
  const set = (key: string, value: string | number | boolean | null) =>
    onChange({ ...params, [key]: value })

  return (
    <div className="form">
      {spec.description && <p className="muted">{spec.description}</p>}
      {spec.fields.filter((f) => visible(f, params)).map((f) => {
        const id = `f-${spec.name}-${f.key}`
        const value = params[f.key]
        if (f.type === 'bool') {
          return (
            <label key={f.key} className="check">
              <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(f.key, e.target.checked)} />
              {f.label}
            </label>
          )
        }
        return (
          <div key={f.key} className="field">
            <label htmlFor={id}>{f.label}{f.required && ' *'}</label>
            {f.type === 'select' ? (
              <select id={id} value={String(value ?? '')} onChange={(e) => set(f.key, e.target.value)}>
                {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : f.type === 'folder' ? (
              <div className="path-add">
                <input id={id} value={String(value ?? '')} placeholder={t('/Pfad/zum/Zielordner')} spellCheck={false}
                  onChange={(e) => set(f.key, e.target.value)} />
                <button onClick={() => setPickerFor(f.key)}>{t('Wählen …')}</button>
                {value ? <button onClick={() => set(f.key, '')}>{t('Leeren')}</button> : null}
              </div>
            ) : f.type === 'number' ? (
              <input id={id} type="number" value={value === null ? '' : Number(value)}
                onChange={(e) => set(f.key, e.target.value === '' ? null : Number(e.target.value))} />
            ) : (
              <input id={id} type={f.type === 'date' ? 'date' : 'text'} value={String(value ?? '')}
                spellCheck={false} onChange={(e) => set(f.key, e.target.value)} />
            )}
            {f.help && <small className="muted">{f.help}</small>}
          </div>
        )
      })}
      {pickerFor && (
        <FolderPicker start={String(params[pickerFor] ?? '')} onClose={() => setPickerFor(null)}
          onPick={(p) => { set(pickerFor, p); setPickerFor(null) }} />
      )}
    </div>
  )
}
