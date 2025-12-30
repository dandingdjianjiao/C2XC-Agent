import { useEffect, useMemo, useRef, useState } from 'react'

export type ConfirmOptions = {
  title: string
  message: React.ReactNode
  details?: React.ReactNode
  confirmText?: string
  cancelText?: string
  intent?: 'primary' | 'danger'
}

type ConfirmState = {
  options: ConfirmOptions
  resolve: (value: boolean) => void
}

export function useConfirmDialog() {
  const [state, setState] = useState<ConfirmState | null>(null)
  const resolveRef = useRef<((value: boolean) => void) | null>(null)

  const confirm = (options: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve
      setState({ options, resolve })
    })
  }

  const close = (value: boolean) => {
    const r = resolveRef.current
    resolveRef.current = null
    setState(null)
    if (r) r(value)
  }

  const dialog = (
    <ConfirmDialog
      open={state !== null}
      options={state?.options}
      onCancel={() => close(false)}
      onConfirm={() => close(true)}
    />
  )

  return { confirm, dialog, isOpen: state !== null }
}

function ConfirmDialog(props: {
  open: boolean
  options?: ConfirmOptions
  onConfirm: () => void
  onCancel: () => void
}) {
  const { open, options, onConfirm, onCancel } = props

  const title = options?.title ?? ''
  const message = options?.message ?? null
  const details = options?.details ?? null
  const intent = options?.intent ?? 'primary'
  const confirmText = options?.confirmText ?? 'Confirm'
  const cancelText = options?.cancelText ?? 'Cancel'

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  const confirmClass =
    intent === 'danger'
      ? 'bg-danger text-accent-fg hover:opacity-90'
      : 'bg-accent text-accent-fg hover:opacity-90'

  const overlayClass = useMemo(() => {
    return open ? 'opacity-100' : 'opacity-0 pointer-events-none'
  }, [open])

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 ${overlayClass}`}>
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onCancel}
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-lg rounded-lg border border-border bg-surface p-4 shadow-lg"
      >
        <div className="text-base font-semibold text-fg">{title}</div>
        <div className="mt-2 text-sm text-muted">{message}</div>

        {details ? (
          <div className="mt-3 rounded-md border border-border bg-bg p-3 text-xs text-fg">
            {details}
          </div>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg hover:border-accent"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-md px-3 py-2 text-sm font-medium ${confirmClass}`}
            autoFocus
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

