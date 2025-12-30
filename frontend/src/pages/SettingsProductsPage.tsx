import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { createProduct, listProducts, updateProduct } from '../api/c2xc'
import type { Product } from '../api/types'
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

export function SettingsProductsPage() {
  const t = useT()
  const queryClient = useQueryClient()

  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')

  const productsQuery = useQuery({
    queryKey: ['products', 'all'],
    queryFn: () => fetchAllProducts(['active', 'archived']),
  })

  const createMutation = useMutation({
    mutationFn: () => createProduct({ name: newName.trim() }),
    onSuccess: () => {
      setNewName('')
      queryClient.invalidateQueries({ queryKey: ['products'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (params: { product_id: string; name?: string; status?: string }) =>
      updateProduct({
        product_id: params.product_id,
        name: params.name ?? null,
        status: params.status ?? null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      queryClient.invalidateQueries({ queryKey: ['product_presets'] })
    },
  })

  const sorted = useMemo(() => {
    const items = productsQuery.data ?? []
    return [...items].sort((a, b) => {
      const sa = a.status === 'active' ? 0 : 1
      const sb = b.status === 'active' ? 0 : 1
      if (sa !== sb) return sa - sb
      return a.name.localeCompare(b.name)
    })
  }, [productsQuery.data])

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-lg font-semibold">{t('nav.settings')}</div>
          <Link
            to="/settings/products"
            className="rounded-md border border-accent bg-bg px-2 py-1 text-xs text-accent"
          >
            {t('settings.products')}
          </Link>
          <Link
            to="/settings/presets"
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
          >
            {t('settings.presets')}
          </Link>
        </div>
      </div>

      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="mb-2 text-sm font-medium text-fg">{t('products.new')}</div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder={t('products.namePlaceholder')}
            className="w-full max-w-md rounded-md border border-border bg-bg px-3 py-2 text-sm text-fg outline-none focus:border-accent"
          />
          <button
            type="button"
            onClick={() => createMutation.mutate()}
            disabled={!newName.trim() || createMutation.isPending}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg hover:border-accent disabled:opacity-50"
          >
            {createMutation.isPending ? t('common.loading') : t('products.create')}
          </button>
        </div>
        {createMutation.error ? (
          <div className="mt-2 text-sm text-danger">
            {t('common.error')}: {(createMutation.error as Error).message}
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-sm font-medium text-fg">{t('products.list')}</div>
          <button
            type="button"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['products'] })}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
          >
            {t('runs.refresh')}
          </button>
        </div>

        {productsQuery.isLoading ? (
          <div className="text-sm text-muted">{t('common.loading')}</div>
        ) : productsQuery.error ? (
          <div className="text-sm text-danger">
            {t('common.error')}: {(productsQuery.error as Error).message}
          </div>
        ) : sorted.length === 0 ? (
          <div className="text-sm text-muted">{t('products.empty')}</div>
        ) : (
          <div className="grid gap-2">
            {sorted.map((p) => {
              const isEditing = editingId === p.product_id
              return (
                <div
                  key={p.product_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-bg px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      {isEditing ? (
                        <input
                          value={editingName}
                          onChange={(e) => setEditingName(e.target.value)}
                          className="w-full max-w-md rounded-md border border-border bg-surface px-2 py-1 text-sm text-fg outline-none focus:border-accent"
                        />
                      ) : (
                        <div className="truncate text-sm text-fg">{p.name}</div>
                      )}
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs ${
                          p.status === 'active'
                            ? 'border-success text-success'
                            : 'border-warn text-warn'
                        }`}
                      >
                        {p.status}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted">
                      {t('common.updatedAt')}: {new Date(p.updated_at * 1000).toLocaleString()}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isEditing ? (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(null)
                            setEditingName('')
                          }}
                          className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
                        >
                          {t('common.cancel')}
                        </button>
                        <button
                          type="button"
                          disabled={!editingName.trim() || updateMutation.isPending}
                          onClick={() => {
                            updateMutation.mutate({ product_id: p.product_id, name: editingName.trim() })
                            setEditingId(null)
                            setEditingName('')
                          }}
                          className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent disabled:opacity-50"
                        >
                          {updateMutation.isPending ? t('common.loading') : t('common.save')}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(p.product_id)
                            setEditingName(p.name)
                          }}
                          className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent"
                        >
                          {t('common.edit')}
                        </button>
                        <button
                          type="button"
                          disabled={updateMutation.isPending}
                          onClick={() => {
                            const next = p.status === 'active' ? 'archived' : 'active'
                            updateMutation.mutate({ product_id: p.product_id, status: next })
                          }}
                          className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-fg hover:border-accent disabled:opacity-50"
                        >
                          {p.status === 'active' ? t('common.archive') : t('common.activate')}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            })}

            {updateMutation.error ? (
              <div className="text-sm text-danger">
                {t('common.error')}: {(updateMutation.error as ApiError).message}
              </div>
            ) : null}
          </div>
        )}
      </section>
    </div>
  )
}
