// Thin client for the FastAPI backend (see backend/ims/api.py).

export class ApiError extends Error {
  kind: 'network' | 'http'
  status?: number

  constructor(message: string, kind: 'network' | 'http', status?: number) {
    super(message)
    this.kind = kind
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError('network', 'network')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail
    // Backend rule messages are in Portuguese; the status fallback is translated by the UI.
    throw new ApiError(typeof detail === 'string' ? detail : String(response.status), 'http', response.status)
  }
  return body as T
}

function json(method: string, payload: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== '') search.set(k, String(v))
  })
  return search.toString()
}

export type ItemInput = {
  description: string
  brand?: string | null
  reference?: string | null
  ean?: string | null
  serial_number?: string | null
  notes?: string | null
}

export type ItemSummary = {
  id: number
  description: string
  brand: string | null
  reference: string | null
  ean: string | null
  active: boolean
  stock_total: number
  locations: string[]
  verified_at: string | null
}

export type ItemList = { total: number; limit: number; offset: number; items: ItemSummary[] }

export type MovementType = 'IN' | 'OUT' | 'MOVE' | 'ADJUST' | 'VERIFY'

export type Movement = {
  id: string
  created_at: string
  type: MovementType | 'IMPORT'
  item_id: number
  from_location: string | null
  to_location: string | null
  qty: number
  reason: string | null
  operator: string | null
  source: 'local' | 'mobile' | 'import'
  voidable: boolean
}

export type Location = {
  id: number
  label: string
  name: string | null
  estante: number | null
  prateleira: string | null
}

export type LocationInput = { estante: number; prateleira: string | null; name?: string | null }

export type ItemDetail = {
  id: number
  description: string
  brand: string | null
  reference: string | null
  ean: string | null
  serial_number: string | null
  notes: string | null
  active: boolean
  verified_at: string | null
  stock_total: number
  stock: { location_id: number; location: string; qty: number }[]
  movements: Movement[]
}

export type ImportReport = {
  sheet: string
  rows: number
  new_items: number
  updated_items: number
  adjusted_stock: number
  issues: string[]
  committed: boolean
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),

  locations: () => request<Location[]>('/api/locations'),

  listItems: (params: Record<string, string | number | undefined>) =>
    request<ItemList>(`/api/items?${query(params)}`),

  item: (id: number) => request<ItemDetail>(`/api/items/${id}`),

  createItem: (body: ItemInput & { id?: number; initial_qty?: number; initial_location_id?: number }) =>
    request<{ id: number }>('/api/items', json('POST', body)),

  updateItem: (id: number, changes: Partial<ItemInput> & { active?: boolean; verified?: boolean }) =>
    request<{ id: number }>(`/api/items/${id}`, json('PATCH', changes)),

  deleteItem: (id: number) => request<{ id: number }>(`/api/items/${id}`, { method: 'DELETE' }),

  createLocation: (body: LocationInput) => request<Location>('/api/locations', json('POST', body)),

  updateLocation: (id: number, body: LocationInput) =>
    request<Location>(`/api/locations/${id}`, json('PATCH', body)),

  deleteLocation: (id: number) => request<{ id: number }>(`/api/locations/${id}`, { method: 'DELETE' }),


  voidMovement: (id: string, operator?: string) =>
    request<{ changed: boolean }>(`/api/movements/${id}/void`, json('POST', { operator })),

  movement: (body: {
    type: MovementType
    item_id: number
    qty?: number
    from_location_id?: number
    to_location_id?: number
    reason?: string
    operator?: string
  }) => request<{ changed: boolean }>('/api/movements', json('POST', body)),

  movements: (params: Record<string, string | number | undefined>) =>
    request<Movement[]>(`/api/movements?${query(params)}`),

  spStatus: () =>
    request<{
      configured: boolean
      signed_in?: boolean
      account?: string | null
      pending?: boolean
      error?: string | null
      share_url?: string
    }>('/api/sharepoint/status'),

  spSignIn: () =>
    request<{ user_code: string; verification_uri: string; message: string }>(
      '/api/sharepoint/sign-in',
      { method: 'POST' },
    ),

  spSetLink: (shareUrl: string) =>
    request<{ share_url?: string }>('/api/sharepoint/settings', json('PUT', { share_url: shareUrl })),

  clearLocalData: (confirm: string) =>
    request<{ deleted: Record<string, number> }>('/api/admin/clear-data', json('POST', { confirm })),

  spSignOut: () => request<{ signed_in?: boolean }>('/api/sharepoint/sign-out', { method: 'POST' }),

  spImport: (mode: 'dry-run' | 'commit') =>
    request<ImportReport & { source: string }>(`/api/sharepoint/import/${mode}`, { method: 'POST' }),

  importFile: (mode: 'dry-run' | 'commit', file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportReport>(`/api/import/${mode}`, { method: 'POST', body: form })
  },
}
