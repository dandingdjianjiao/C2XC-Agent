import type { ErrorEnvelope } from './types'

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(args: { status: number; code: string; message: string; details?: unknown }) {
    super(args.message)
    this.name = 'ApiError'
    this.status = args.status
    this.code = args.code
    this.details = args.details
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'

function joinPath(base: string, path: string): string {
  const b = base.endsWith('/') ? base.slice(0, -1) : base
  const p = path.startsWith('/') ? path : `/${path}`
  return `${b}${p}`
}

function buildUrl(path: string, query?: Record<string, unknown>): string {
  const url = new URL(joinPath(API_BASE, path), window.location.origin)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null) continue
      if (Array.isArray(v)) {
        for (const item of v) {
          url.searchParams.append(k, String(item))
        }
      } else {
        url.searchParams.set(k, String(v))
      }
    }
  }
  return url.toString()
}

async function safeReadJson(resp: Response): Promise<unknown | null> {
  const contentType = resp.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return null
  try {
    return await resp.json()
  } catch {
    return null
  }
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit & { query?: Record<string, unknown> },
): Promise<T> {
  const url = buildUrl(path, options?.query)
  const resp = await fetch(url, {
    ...options,
    headers: {
      'content-type': 'application/json',
      ...(options?.headers ?? {}),
    },
  })

  const json = await safeReadJson(resp)
  if (!resp.ok) {
    const env = json as ErrorEnvelope | null
    const code = env?.error?.code ?? 'http_error'
    const message = env?.error?.message ?? `HTTP ${resp.status}`
    const details = env?.error?.details
    throw new ApiError({ status: resp.status, code, message, details })
  }

  return (json ?? null) as T
}

