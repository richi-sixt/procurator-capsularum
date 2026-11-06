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
