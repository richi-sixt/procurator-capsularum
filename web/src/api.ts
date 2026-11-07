import type { Prefs } from './i18n'
import type {
  About, Batch, Browse, Config, ConfigResponse, HelpContent, HelpPage, Job, Learning, ProbeResult, SendPreview, OperationSpec, Params, PlanResponse, Preset,
} from './types'

// Sprache der Meldungen vom Server (Kopf `X-Lang`), gesetzt vom I18nProvider
let apiLang = 'de'
export const setApiLang = (lang: string) => { apiLang = lang }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', 'X-Lang': apiLang },
    ...init,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') msg = body.detail
    } catch { /* kein JSON */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export type PlanInput = {
  paths: string[]
  recursive: boolean
  operation: string
  params: Params
  force_unique: boolean
  order: string[] | null
  confirm_cloud?: boolean
}

const post = (body: unknown, signal?: AbortSignal): RequestInit => ({
  method: 'POST', body: JSON.stringify(body), signal,
})

export const api = {
  operations: () => call<OperationSpec[]>('/operations'),
  browse: (path: string) => call<Browse>(`/browse?path=${encodeURIComponent(path)}`),
  scan: (paths: string[], recursive: boolean, signal?: AbortSignal) =>
    call<{ src: string; srcName: string; folder: string }[]>('/scan', post({ paths, recursive }, signal)),
  plan: (input: PlanInput, signal?: AbortSignal) => call<PlanResponse>('/plan', post(input, signal)),
  apply: (input: PlanInput, disabled: string[]) =>
    call<Job>('/apply', post({ ...input, disabled })),
  analyze: (input: PlanInput) => call<Job>('/analyze', post(input)),
  analyzePreview: (input: PlanInput) => call<SendPreview>('/analyze/preview', post(input)),
  editProposal: (input: PlanInput, path: string, target: string) =>
    call<{ ok: boolean }>('/proposals/edit', post({ ...input, path, target })),
  job: (id: string) => call<Job>(`/jobs/${id}`),
  cancelJob: (id: string) => call<{ ok: boolean }>(`/jobs/${id}/cancel`, { method: 'POST' }),
  reveal: (path: string) => call<{ ok: boolean }>('/reveal', post({ path })),
  prefs: () => call<Prefs>('/prefs'),
  savePrefs: (patch: Partial<Prefs>) => call<Prefs>('/prefs', { method: 'PUT', body: JSON.stringify(patch) }),
  history: () => call<Batch[]>('/history'),
  historyDetail: (id: number) =>
    call<{ src: string; dst: string; folder: string }[]>(`/history/${id}`),
  undo: (id: number) =>
    call<{ restored: number; errors: string[] }>(`/undo/${id}`, { method: 'POST' }),
  helpPages: () => call<HelpPage[]>('/help'),
  helpPage: (name: string) => call<HelpContent>(`/help/${encodeURIComponent(name)}`),
  about: () => call<About>('/about'),
  learning: () => call<Learning>('/learning'),
  clearLearning: () => call<{ deleted: number }>('/learning', { method: 'DELETE' }),
  config: () => call<ConfigResponse>('/config'),
  saveConfig: (c: Config) => call<ConfigResponse>('/config', { method: 'PUT', body: JSON.stringify(c) }),
  testConfig: (c: Config) => call<ProbeResult>('/config/test', post(c)),
  presets: () => call<Preset[]>('/presets'),
  savePreset: (p: Preset) => call<{ ok: boolean }>('/presets', post(p)),
  deletePreset: (name: string) =>
    call<{ ok: boolean }>(`/presets/${encodeURIComponent(name)}`, { method: 'DELETE' }),
}
