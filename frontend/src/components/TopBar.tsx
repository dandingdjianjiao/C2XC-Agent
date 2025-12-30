import { Link } from 'react-router-dom'
import { useT } from '../i18n/i18n'
import { useTheme } from '../theme/theme'
import { useI18n } from '../i18n/i18n'
import { useQuery } from '@tanstack/react-query'
import { getSystemWorker } from '../api/c2xc'

export function TopBar() {
  const t = useT()
  const { theme, toggleTheme } = useTheme()
  const { lang, toggleLang } = useI18n()
  const workerQuery = useQuery({
    queryKey: ['systemWorker'],
    queryFn: () => getSystemWorker(),
    refetchInterval: 2000,
  })

  const worker = workerQuery.data?.worker
  const queue = workerQuery.data?.queue
  const runsQueued = queue?.runs_by_status?.queued ?? 0
  const runsRunning = queue?.runs_by_status?.running ?? 0
  const batchesQueued = queue?.batches_by_status?.queued ?? 0
  const batchesRunning = queue?.batches_by_status?.running ?? 0
  const rbQueued = queue?.rb_jobs_by_status?.queued ?? 0
  const rbRunning = queue?.rb_jobs_by_status?.running ?? 0

  const workerStatus =
    workerQuery.isError
      ? 'api_error'
      : !worker
        ? 'loading'
        : worker.enabled && worker.running
          ? 'running'
          : worker.enabled && !worker.running
            ? 'stopped'
            : 'disabled'

  const workerLabel =
    workerStatus === 'running'
      ? `worker: running · runs q=${runsQueued} r=${runsRunning}`
      : workerStatus === 'stopped'
        ? `worker: not running · runs q=${runsQueued} r=${runsRunning}`
        : workerStatus === 'disabled'
          ? `worker: disabled · runs q=${runsQueued} r=${runsRunning}`
          : workerStatus === 'api_error'
            ? 'worker: API error'
            : 'worker: loading…'

  const workerDotClass =
    workerStatus === 'running'
      ? 'bg-success'
      : workerStatus === 'loading'
        ? 'bg-muted'
        : workerStatus === 'api_error'
          ? 'bg-danger'
          : 'bg-warn'

  const bannerText =
    workerStatus === 'disabled'
      ? t('banner.workerDisabled')
      : workerStatus === 'stopped'
        ? t('banner.workerStopped')
        : workerStatus === 'api_error'
          ? t('banner.workerApiError')
          : ''

  return (
    <header className="sticky top-0 z-10 border-b border-border bg-bg backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <Link to="/" className="font-semibold tracking-tight text-fg">
            {t('app.title')}
          </Link>
          <Link to="/" className="text-xs text-muted hover:text-fg">
            {t('nav.runs')}
          </Link>
          <Link to="/memories" className="text-xs text-muted hover:text-fg">
            {t('nav.memories')}
          </Link>
          <Link to="/settings/products" className="text-xs text-muted hover:text-fg">
            {t('nav.settings')}
          </Link>
          <span
            className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-2 py-1 text-[11px] text-muted"
            title={`${workerLabel}\n\nbatches q=${batchesQueued} r=${batchesRunning}\nrb_jobs q=${rbQueued} r=${rbRunning}`}
          >
            <span className={`h-2 w-2 rounded-full ${workerDotClass}`} />
            <span className="font-mono">
              q:{runsQueued} r:{runsRunning}
            </span>
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleLang}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
            title={t('settings.lang')}
          >
            {lang === 'en' ? t('settings.en') : t('settings.zh')}
          </button>
          <button
            type="button"
            onClick={toggleTheme}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
            title={t('settings.theme')}
          >
            {theme === 'light' ? t('settings.light') : t('settings.dark')}
          </button>
        </div>
      </div>

      {bannerText ? (
        <div className="border-t border-warn bg-surface">
          <div className="mx-auto w-full max-w-6xl px-4 py-2 text-xs text-warn">{bannerText}</div>
        </div>
      ) : null}
    </header>
  )
}
