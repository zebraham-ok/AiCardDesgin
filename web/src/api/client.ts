const BASE = '/api'

async function req<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init
  })
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = j.detail || j.message || msg
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  get: <T = any>(p: string) => req<T>(p),
  post: <T = any>(p: string, body?: any) =>
    req<T>(p, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T = any>(p: string, body?: any) =>
    req<T>(p, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  patch: <T = any>(p: string, body?: any) =>
    req<T>(p, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  del: <T = any>(p: string) => req<T>(p, { method: 'DELETE' }),
  upload: async <T = any>(p: string, form: FormData) => {
    const res = await fetch(BASE + p, { method: 'POST', body: form })
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText)
    return res.json() as T
  }
}

export const assetUrl = (id: string | null | undefined) =>
  id ? `${BASE}/assets/${id}/file` : ''

/**
 * 缩略图 URL（列表 / 选择器用）。
 * 服务端没生成缩略图（SVG、字体、老资源）时会自动退回原文件，所以可以无条件用它。
 */
export const thumbUrl = (id: string | null | undefined) =>
  id ? `${BASE}/assets/${id}/thumb` : ''

/** asset://xxx 或裸 id 统一解析为可访问 URL */
export const resolveAsset = (v: any) => {
  if (!v) return ''
  const s = String(v)
  return s.startsWith('asset://') ? assetUrl(s.slice(8)) : assetUrl(s)
}

export const toAssetUri = (id: string) => `asset://${id}`
