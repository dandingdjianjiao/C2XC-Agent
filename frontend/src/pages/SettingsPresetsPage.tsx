import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createProductPreset, listProductPresets, listProducts, updateProductPreset } from '../api/c2xc'
import type { Product, ProductPreset } from '../api/types'
import { useT } from '../i18n/i18n'

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

export function SettingsPresetsPage() {
  const t = useT()
  const queryClient = useQueryClient()

  const productsQuery = useQuery({
    queryKey: ['products', 'active'],
    queryFn: () => fetchAllProducts(['active']),
  })

  const presetsQuery = useQuery({
    queryKey: ['product_presets', 'all'],
    queryFn: () => fetchAllPresets(['active', 'archived']),
  })

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [selectedProducts, setSelectedProducts] = useState<Record<string, boolean>>({})

  const selectedPreset = useMemo(() => {
    const list = presetsQuery.data ?? []
    return selectedId ? list.find((p) => p.preset_id === selectedId) ?? null : null
  }, [presetsQuery.data, selectedId])

  const createMutation = useMutation({
    mutationFn: () =>
      createProductPreset({
        name: name.trim(),
        product_ids: Object.entries(selectedProducts)
          .filter(([, v]) => v)
          .map(([k]) => k),
      }),
    onSuccess: () => {
      setSelectedId(null)
      setName('')
      setSelectedProducts({})
      queryClient.invalidateQueries({ queryKey: ['product_presets'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (params: { preset_id: string; name: string; product_ids: string[]; status?: string }) =>
      updateProductPreset({
        preset_id: params.preset_id,
        name: params.name,
        product_ids: params.product_ids,
        status: params.status ?? null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product_presets'] })
    },
  })

  const sortedPresets = useMemo(() => {
    const items = presetsQuery.data ?? []
    return [...items].sort((a, b) => {
      const sa = a.status === 'active' ? 0 : 1
      const sb = b.status === 'active' ? 0 : 1
      if (sa !== sb) return sa - sb
      return a.name.localeCompare(b.name)
    })
  }, [presetsQuery.data])

  const products = useMemo(() => {
    return [...(productsQuery.data ?? [])].sort((a, b) => a.name.localeCompare(b.name))
  }, [productsQuery.data])

  const selectedCount = Object.values(selectedProducts).filter(Boolean).length

  const submitDisabled = !name.trim() || selectedCount === 0

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-lg font-semibold">{t('nav.settings')}</div>
          <Link
            to="/settings/products"
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
          >
            {t('settings.products')}
          </Link>
          <Link
            to="/settings/presets"
            className="rounded-md border border-accent bg-bg px-2 py-1 text-xs text-accent"
          >
            {t('settings.presets')}
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-fg">{t('presets.list')}</div>
            <button
              type="button"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['product_presets'] })}
              className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
            >
              {t('runs.refresh')}
            </button>
          </div>

          {presetsQuery.isLoading ? (
            <div className="text-sm text-muted">{t('common.loading')}</div>
          ) : presetsQuery.error ? (
            <div className="text-sm text-danger">
              {t('common.error')}: {(presetsQuery.error as Error).message}
            </div>
          ) : sortedPresets.length === 0 ? (
            <div className="text-sm text-muted">{t('presets.empty')}</div>
          ) : (
            <div className="grid gap-2">
              {sortedPresets.map((p) => (
                <button
                  key={p.preset_id}
                  type="button"
                  onClick={() => {
                    setSelectedId(p.preset_id)
                    setName(p.name)
                    const next: Record<string, boolean> = {}
                    for (const pid of p.product_ids ?? []) next[pid] = true
                    setSelectedProducts(next)
                  }}
                  className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left ${
                    selectedId === p.preset_id
                      ? 'border-accent bg-bg'
                      : 'border-border bg-bg hover:border-accent'
                  }`}
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm text-fg">{p.name}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {t('presets.count')}: {p.product_ids?.length ?? 0}
                    </div>
                  </div>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-xs ${
                      p.status === 'active' ? 'border-success text-success' : 'border-warn text-warn'
                    }`}
                  >
                    {p.status}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-lg border border-border bg-surface p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-fg">
              {selectedPreset ? t('presets.edit') : t('presets.new')}
            </div>
            <div className="flex items-center gap-2">
              {selectedPreset ? (
                <button
                  type="button"
                  onClick={() => {
                    setSelectedId(null)
                    setName('')
                    setSelectedProducts({})
                  }}
                  className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
                >
                  {t('common.new')}
                </button>
              ) : null}
            </div>
          </div>

          <div className="grid gap-3">
            <div>
              <div className="mb-1 text-xs font-medium text-muted">{t('presets.name')}</div>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('presets.namePlaceholder')}
                className="w-full rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg outline-none focus:border-accent"
              />
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <div className="text-xs font-medium text-muted">{t('presets.products')}</div>
                <div className="text-xs text-muted">
                  {t('presets.selected')}: {selectedCount}
                </div>
              </div>

              {productsQuery.isLoading ? (
                <div className="text-sm text-muted">{t('common.loading')}</div>
              ) : productsQuery.error ? (
                <div className="text-sm text-danger">
                  {t('common.error')}: {(productsQuery.error as Error).message}
                </div>
              ) : products.length === 0 ? (
                <div className="text-sm text-muted">{t('presets.noProducts')}</div>
              ) : (
                <div className="max-h-72 overflow-auto rounded-md border border-border bg-bg p-2">
                  <div className="grid gap-1">
                    {products.map((p) => (
                      <label key={p.product_id} className="flex items-center gap-2 text-sm text-fg">
                        <input
                          type="checkbox"
                          checked={Boolean(selectedProducts[p.product_id])}
                          onChange={(e) => {
                            const next = { ...selectedProducts }
                            next[p.product_id] = e.target.checked
                            setSelectedProducts(next)
                          }}
                        />
                        <span className="truncate">{p.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {selectedPreset ? (
                <>
                  <button
                    type="button"
                    disabled={updateMutation.isPending}
                    onClick={() => {
                      const next = selectedPreset.status === 'active' ? 'archived' : 'active'
                      updateMutation.mutate({
                        preset_id: selectedPreset.preset_id,
                        name: selectedPreset.name,
                        product_ids: selectedPreset.product_ids,
                        status: next,
                      })
                    }}
                    className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-accent disabled:opacity-50"
                  >
                    {selectedPreset.status === 'active' ? t('common.archive') : t('common.activate')}
                  </button>
                  <button
                    type="button"
                    disabled={submitDisabled || updateMutation.isPending}
                    onClick={() => {
                      updateMutation.mutate({
                        preset_id: selectedPreset.preset_id,
                        name: name.trim(),
                        product_ids: Object.entries(selectedProducts)
                          .filter(([, v]) => v)
                          .map(([k]) => k),
                      })
                    }}
                    className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-accent disabled:opacity-50"
                  >
                    {updateMutation.isPending ? t('common.loading') : t('common.save')}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  disabled={submitDisabled || createMutation.isPending}
                  onClick={() => createMutation.mutate()}
                  className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-accent disabled:opacity-50"
                >
                  {createMutation.isPending ? t('common.loading') : t('presets.create')}
                </button>
              )}
            </div>

            {createMutation.error ? (
              <div className="text-sm text-danger">
                {t('common.error')}: {(createMutation.error as ApiError).message}
              </div>
            ) : null}

            {updateMutation.error ? (
              <div className="text-sm text-danger">
                {t('common.error')}: {(updateMutation.error as ApiError).message}
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  )
}
