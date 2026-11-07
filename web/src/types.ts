export type FieldOption = { value: string; label: string }

export type Field = {
  key: string
  label: string
  type: 'text' | 'number' | 'select' | 'bool' | 'date' | 'folder'
  default: string | number | boolean | null
  options: FieldOption[]
  help: string
  required: boolean
  showIf: Record<string, string> | null
}

export type OperationSpec = {
  name: string
  label: string
  group: string
  kind: 'move' | 'convert'
  needsAnalysis?: boolean
  sendsData?: boolean
  description: string
  fields: Field[]
}

export type Status = 'ok' | 'skip' | 'conflict' | 'error'

export type Change = {
  src: string
  srcName: string
  dst: string | null
  dstName: string | null
  dstFolder?: string | null
  folder: string
  status: Status
  reason: string
  sensitive?: string
  editable?: string | null
  related?: string[] // gleiche Dateien (Dubletten), die behaltene zuerst
  relatedTotal?: number
}

export type PlanResponse = {
  operation: string
  kind?: 'move' | 'convert'
  counts: Record<Status, number>
  sensitiveCount?: number
  info?: Record<string, number | string>
  needsAnalysis?: boolean
  changes: Change[]
}

export type Params = Record<string, string | number | boolean | null>

export type Batch = {
  id: number; ts: string; operation: string; count: number; undone: boolean; kind: 'move' | 'convert'
}
export type Preset = { name: string; operation: string; params: Params }
export type Browse = { path: string; parent: string | null; home: string; dirs: string[]; fileCount: number }
export type Job = {
  id: string
  state: 'running' | 'finished' | 'cancelled' | 'error'
  total: number
  done: number
  current: string
  batchId: number | null
  ok: number
  failed: { src: string; error: string }[]
  skipped: number
  error: string
}

export type AiConfig = {
  provider: 'ollama' | 'claude'
  ollama_model: string
  ollama_host: string
  claude_model: string
  api_key_env: string
  privacy_level: number
  learn: boolean
}
export type PrivacyConfig = {
  sensitive_keywords: string[]
  sensitive_extensions: string[]
  allow_sensitive_local: boolean
}
export type Config = { ai: AiConfig; privacy: PrivacyConfig }
export type ConfigResponse = {
  config: Config
  defaults: Config
  warning: string | null
  isCloud: boolean
  requiresConfirmation: boolean
  apiKeyPresent: boolean
  privacyLevels: Record<string, string>
  path: string
}
export type ProbeResult = { ok: boolean; message: string; models: string[]; provider: string }

export type SendPreview = {
  needed: boolean
  provider?: string
  model?: string
  isCloud?: boolean
  privacyLevel?: number
  privacyText?: string
  files?: number
  withheld?: number
  cached?: number
  batches?: number
  sample?: Record<string, unknown>[]
  needsConfirmation?: boolean
  learning?: { examples: number; habits: number; rejected: number; text: string }
}

export type Learning = {
  stats: { accepted: number; edited: number; rejected: number; total: number }
  recent: { kind: string; name: string; to_folder: string; to_name: string }[]
}

export type Component = { name: string; version: string; license: string; optional: boolean }
export type About = {
  name: string
  version: string
  author: string
  copyright: string
  license: { id: string; name: string; url: string }
  notice: string
  repository: string
  inspiration: { name: string; url?: string; note: string }[]
  external: { name: string; url: string; note: string }[]
  components: { python: Component[]; frontend: Component[] }
  system: { python: string; platform: string }
}

export type HelpPage = { name: string; title: string }
export type HelpToc = { level: number; id: string; text: string }
export type HelpContent = { name: string; title: string; html: string; toc: HelpToc[] }
