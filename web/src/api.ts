import type {
  Batch, Browse, Config, ConfigResponse, Job, ProbeResult, OperationSpec, Params, PlanResponse, Preset,
} from './types'

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
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
  job: (id: string) => call<Job>(`/jobs/${id}`),
  cancelJob: (id: string) => call<{ ok: boolean }>(`/jobs/${id}/cancel`, { method: 'POST' }),
  history: () => call<Batch[]>('/history'),
  historyDetail: (id: number) =>
    call<{ src: string; dst: string; folder: string }[]>(`/history/${id}`),
  undo: (id: number) =>
    call<{ restored: number; errors: string[] }>(`/undo/${id}`, { method: 'POST' }),
  config: () => call<ConfigResponse>('/config'),
  saveConfig: (c: Config) => call<ConfigResponse>('/config', { method: 'PUT', body: JSON.stringify(c) }),
  testConfig: (c: Config) => call<ProbeResult>('/config/test', post(c)),
  presets: () => call<Preset[]>('/presets'),
  savePreset: (p: Preset) => call<{ ok: boolean }>('/presets', post(p)),
  deletePreset: (name: string) =>
    call<{ ok: boolean }>(`/presets/${encodeURIComponent(name)}`, { method: 'DELETE' }),
}
