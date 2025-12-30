import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { ApiError } from '../api/client'
import { getRunFeedback, listProductPresets, listProducts, upsertRunFeedback } from '../api/c2xc'
import type { Product, ProductPreset, RunFeedback, RunFeedbackResponse } from '../api/types'
import { useT } from '../i18n/i18n'

type DraftRow = { product_id: string; value: string }

async function fetchAllProducts(status?: string[]): Promise<Product[]> {
  const items: Product[] = []
  let cursor: string | null = null
  for (let i = 0; i < 50; i++) {
    const page = await listProducts({ limit: 200, cursor, status })
    items.push(...(page.items ?? []))
    if (!page.has_more || !page.next_cursor) break
    cursor = page.next_cursor
  }
  return items
}

async function fetchAllPresets(status?: string[]): Promise<ProductPreset[]> {
  const items: ProductPreset[] = []
  let cursor: string | null = null
  for (let i = 0; i < 50; i++) {
    const page = await listProductPresets({ limit: 200, cursor, status })
    items.push(...(page.items ?? []))
    if (!page.has_more || !page.next_cursor) break
    cursor = page.next_cursor
  }
  return items
}

function parseFiniteNumber(text: string): number | null {
  const s = (text ?? '').trim()
  if (!s) return null
  const n = Number(s)
  if (!Number.isFinite(n)) return null
  return n
}

function formatTs(ts: number | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts * 1000).toLocaleString()
  } catch {
    return String(ts)
  }
}

export function FeedbackTab(props: { runId: string }) {
  const t = useT()
  const runId = props.runId

  const productsQuery = useQuery({
    queryKey: ['products', 'allForFeedback'],
    queryFn: () => fetchAllProducts(['active', 'archived']),
  })

  const presetsQuery = useQuery({
    queryKey: ['product_presets', 'activeForFeedback'],
    queryFn: () => fetchAllPresets(['active']),
  })

  const feedbackQuery = useQuery({
    queryKey: ['feedback', runId],
    queryFn: async (): Promise<RunFeedbackResponse | null> => {
      try {
        return await getRunFeedback(runId)
      } catch (err) {
        if (err instanceof ApiError && err.code === 'not_found') return null
        throw err
      }
    },
    enabled: !!runId,
  })

  const sortedProducts = useMemo(() => {
    const items = productsQuery.data ?? []
    return [...items].sort((a, b) => {
      const sa = a.status === 'active' ? 0 : 1
      const sb = b.status === 'active' ? 0 : 1
      if (sa !== sb) return sa - sb
      return a.name.localeCompare(b.name)
    })
  }, [productsQuery.data])

  if (feedbackQuery.isLoading) {
    return <div className="text-sm text-muted">{t('common.loading')}</div>
  }
  if (feedbackQuery.error) {
    return (
      <div className="rounded-md border border-danger bg-bg p-3 text-sm text-danger">
        {t('common.error')}: {(feedbackQuery.error as Error).message}
      </div>
    )
  }

  const initialFeedback: RunFeedback | null = feedbackQuery.data?.feedback ?? null
  const key = `${runId}:${initialFeedback?.feedback_id ?? 'none'}`

  return (
    <FeedbackEditor
      key={key}
      runId={runId}
      initialFeedback={initialFeedback}
      products={sortedProducts}
      presets={presetsQuery.data ?? []}
    />
  )
}

function FeedbackEditor(props: {
  runId: string
  initialFeedback: RunFeedback | null
  products: Product[]
  presets: ProductPreset[]
}) {
  const t = useT()
  const queryClient = useQueryClient()

  const runId = props.runId
  const initial = props.initialFeedback

  const [scoreText, setScoreText] = useState(() => (initial?.score === null || initial?.score === undefined ? '' : String(initial.score)))
  const [pros, setPros] = useState(() => initial?.pros ?? '')
  const [cons, setCons] = useState(() => initial?.cons ?? '')
  const [other, setOther] = useState(() => initial?.other ?? '')
  const [rows, setRows] = useState<DraftRow[]>(
    () => (initial?.products ?? []).map((p) => ({ product_id: p.product_id, value: String(p.value) })) ?? [],
  )
  const [presetToApply, setPresetToApply] = useState<string>('')

  const productById = useMemo(() => {
    const m = new Map<string, Product>()
    for (const p of props.products) m.set(p.product_id, p)
    return m
  }, [props.products])

  const draftScore = useMemo(() => {
    const n = parseFiniteNumber(scoreText)
    return n === null ? null : n
  }, [scoreText])

  const validation = useMemo(() => {
    const errors: string[] = []
    const normalized: { product_id: string; value: number }[] = []
    const seen = new Set<string>()

    for (const [i, r] of rows.entries()) {
      const pid = (r.product_id ?? '').trim()
      if (!pid) {
        errors.push(`${t('feedback.errorRow')} #${i + 1}: ${t('feedback.errorMissingProduct')}`)
        continue
      }
      if (seen.has(pid)) {
        errors.push(`${t('feedback.errorRow')} #${i + 1}: ${t('feedback.errorDuplicateProduct')}`)
        continue
      }
      seen.add(pid)

      const n = parseFiniteNumber(r.value)
      if (n === null) {
        errors.push(`${t('feedback.errorRow')} #${i + 1}: ${t('feedback.errorMissingValue')}`)
        continue
      }
      if (n < 0) {
        errors.push(`${t('feedback.errorRow')} #${i + 1}: ${t('feedback.errorNegative')}`)
        continue
      }
      normalized.push({ product_id: pid, value: n })
    }

    const total = normalized.reduce((acc, x) => acc + x.value, 0)
    const fractions: Record<string, number> = {}
    if (total > 0) {
      for (const x of normalized) fractions[x.product_id] = x.value / total
    } else {
      for (const x of normalized) fractions[x.product_id] = 0
    }

    return { errors, normalized, total, fractions }
  }, [rows, t])

  const saveMutation = useMutation({
    mutationFn: () =>
      upsertRunFeedback({
        run_id: runId,
        score: draftScore,
        pros,
        cons,
        other,
        products: validation.normalized,
      }),
    onSuccess: (resp) => {
      queryClient.setQueryData(['feedback', runId], resp)
      queryClient.invalidateQueries({ queryKey: ['feedback', runId] })
    },
  })

  const hasSumZeroWarning = validation.normalized.length > 0 && validation.total === 0

  const canSave =
    !saveMutation.isPending && validation.errors.length === 0 && (draftScore === null || Number.isFinite(draftScore))

  const handleApplyPreset = () => {
    const preset = (props.presets ?? []).find((p) => p.preset_id === presetToApply)
    if (!preset) return
    setRows((preset.product_ids ?? []).map((pid) => ({ product_id: pid, value: '' })))
  }

  return (
    <div className="grid gap-4">
      <div className="grid gap-1 text-sm">
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          <div>
            <span className="text-muted">{t('feedback.updatedAt')}:</span>{' '}
            {formatTs(initial?.updated_at ?? null)}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-border bg-bg p-4">
          <div className="mb-2 text-sm font-medium text-fg">{t('feedback.meta')}</div>

          <div className="grid gap-3">
            <div>
              <div className="mb-1 text-xs font-medium text-muted">{t('feedback.score')}</div>
              <input
                value={scoreText}
                onChange={(e) => setScoreText(e.target.value)}
                placeholder={t('feedback.scoreHint')}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent"
              />
            </div>

            <div>
              <div className="mb-1 text-xs font-medium text-muted">{t('feedback.pros')}</div>
              <textarea
                value={pros}
                onChange={(e) => setPros(e.target.value)}
                rows={4}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent"
              />
            </div>

            <div>
              <div className="mb-1 text-xs font-medium text-muted">{t('feedback.cons')}</div>
              <textarea
                value={cons}
                onChange={(e) => setCons(e.target.value)}
                rows={4}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent"
              />
            </div>

            <div>
              <div className="mb-1 text-xs font-medium text-muted">{t('feedback.other')}</div>
              <textarea
                value={other}
                onChange={(e) => setOther(e.target.value)}
                rows={3}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-accent"
              />
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-border bg-bg p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium text-fg">{t('feedback.products')}</div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={presetToApply}
                onChange={(e) => setPresetToApply(e.target.value)}
                className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg outline-none focus:border-accent"
              >
                <option value="">{t('feedback.preset')}</option>
                {(props.presets ?? []).map((p) => (
                  <option key={p.preset_id} value={p.preset_id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleApplyPreset}
                disabled={!presetToApply}
                className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent disabled:opacity-50"
              >
                {t('feedback.applyPreset')}
              </button>
              <button
                type="button"
                onClick={() => setRows((r) => [...r, { product_id: '', value: '' }])}
                className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
              >
                {t('feedback.addProduct')}
              </button>
            </div>
          </div>

          {props.products.length === 0 ? (
            <div className="text-sm text-muted">{t('feedback.noProducts')}</div>
          ) : (
            <div className="grid gap-2">
              {rows.length === 0 ? (
                <div className="text-sm text-muted">{t('feedback.noRows')}</div>
              ) : null}

              {rows.map((r, idx) => {
                const pid = (r.product_id ?? '').trim()
                const product = pid ? productById.get(pid) ?? null : null
                const frac = pid ? validation.fractions[pid] ?? 0 : 0
                const fracPct = `${Math.round(frac * 1000) / 10}%`

                return (
                  <div
                    key={`${idx}-${pid}`}
                    className="grid grid-cols-1 gap-2 rounded-md border border-border bg-surface p-2 md:grid-cols-12"
                  >
                    <div className="md:col-span-6">
                      <div className="mb-1 text-[11px] font-medium text-muted">{t('feedback.product')}</div>
                      <select
                        value={r.product_id}
                        onChange={(e) => {
                          const next = [...rows]
                          next[idx] = { ...next[idx], product_id: e.target.value }
                          setRows(next)
                        }}
                        className="w-full rounded-md border border-border bg-bg px-2 py-1 text-sm text-fg outline-none focus:border-accent"
                      >
                        <option value="">{t('feedback.selectProduct')}</option>
                        {props.products.map((p) => (
                          <option key={p.product_id} value={p.product_id}>
                            {p.status === 'archived' ? `${p.name} (${t('common.archived')})` : p.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="md:col-span-3">
                      <div className="mb-1 text-[11px] font-medium text-muted">{t('feedback.value')}</div>
                      <input
                        value={r.value}
                        onChange={(e) => {
                          const next = [...rows]
                          next[idx] = { ...next[idx], value: e.target.value }
                          setRows(next)
                        }}
                        placeholder="0"
                        className="w-full rounded-md border border-border bg-bg px-2 py-1 text-sm text-fg outline-none focus:border-accent"
                      />
                    </div>

                    <div className="md:col-span-2">
                      <div className="mb-1 text-[11px] font-medium text-muted">{t('feedback.fraction')}</div>
                      <div className="rounded-md border border-border bg-bg px-2 py-1 text-sm text-fg">
                        {fracPct}
                      </div>
                    </div>

                    <div className="md:col-span-1 md:flex md:items-end md:justify-end">
                      <button
                        type="button"
                        onClick={() => setRows((xs) => xs.filter((_, i) => i !== idx))}
                        className="rounded-md border border-border bg-bg px-2 py-1 text-xs text-fg hover:border-danger"
                        title={t('common.remove')}
                      >
                        ×
                      </button>
                    </div>

                    {product && product.status === 'archived' ? (
                      <div className="md:col-span-12 text-xs text-warn">
                        {t('feedback.archivedWarning')}
                      </div>
                    ) : null}
                  </div>
                )
              })}

              {hasSumZeroWarning ? (
                <div className="rounded-md border border-warn bg-bg p-3 text-sm text-warn">
                  {t('feedback.sumZero')}
                </div>
              ) : null}

              {validation.errors.length ? (
                <div className="rounded-md border border-danger bg-bg p-3 text-sm text-danger">
                  {validation.errors.map((e) => (
                    <div key={e}>{e}</div>
                  ))}
                </div>
              ) : null}

              {saveMutation.error ? (
                <div className="rounded-md border border-danger bg-bg p-3 text-sm text-danger">
                  {t('common.error')}: {(saveMutation.error as Error).message}
                </div>
              ) : null}

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => saveMutation.mutate()}
                  disabled={!canSave}
                  className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-accent disabled:opacity-50"
                >
                  {saveMutation.isPending ? t('common.loading') : t('feedback.save')}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
