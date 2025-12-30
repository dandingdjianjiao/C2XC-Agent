import { ApiError } from '../api/client'
import { useT } from '../i18n/i18n'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === 'string')
}

function extractMissing(error: ApiError): string[] {
  const details = error.details
  if (!isRecord(details)) return []
  const missing = details['missing']
  if (isStringArray(missing)) return missing
  return []
}

export function DependencyUnavailablePanel(props: { error: ApiError }) {
  const t = useT()
  const missing = extractMissing(props.error)

  return (
    <div className="rounded-md border border-warn bg-bg p-3 text-sm text-fg">
      <div className="font-medium text-warn">{t('error.deps.title')}</div>
      <div className="mt-1 text-xs text-muted">{t('error.deps.message')}</div>

      {missing.length ? (
        <div className="mt-3 grid gap-2">
          <div className="text-xs font-medium text-muted">{t('error.deps.missing')}</div>
          <ul className="grid list-disc gap-1 pl-5 text-xs text-fg">
            {missing.map((m) => (
              <li key={m} className="font-mono">
                {m}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-3 rounded-md border border-border bg-surface p-3 text-xs text-fg">
        <div className="mb-1 font-medium text-muted">{t('error.deps.fix')}</div>
        <div className="text-muted">{t('error.deps.fixHint')}</div>
        <pre className="mt-2 overflow-auto whitespace-pre-wrap rounded-md border border-border bg-bg p-2 font-mono text-[11px]">
export OPENAI_API_KEY=...
export LIGHTRAG_KB_PRINCIPLES_DIR=/abs/path/to/data/lightrag/kb_principles
export LIGHTRAG_KB_MODULATION_DIR=/abs/path/to/data/lightrag/kb_modulation
        </pre>
        <div className="mt-2 text-muted">{t('error.deps.dryRunTip')}</div>
      </div>
    </div>
  )
}
