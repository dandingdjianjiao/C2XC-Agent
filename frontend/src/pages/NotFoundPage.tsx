import { Link } from 'react-router-dom'
import { useT } from '../i18n/i18n'

export function NotFoundPage() {
  const t = useT()
  return (
    <div className="rounded-lg border border-border bg-surface p-6">
      <div className="text-lg font-semibold">404</div>
      <div className="mt-2 text-sm text-muted">Page not found.</div>
      <div className="mt-4">
        <Link
          to="/"
          className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg hover:border-accent"
        >
          {t('nav.runs')}
        </Link>
      </div>
    </div>
  )
}

