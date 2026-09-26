/** 统一请求封装：拼后端地址、带操作员身份、把后端的拦截原因抛成可读的错误。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const session = useSessionStore()
  // 请求头只能携带拉丁字符，中文操作员与角色按 URL 百分号编码传输，由后端解码。
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Operator-Name': encodeURIComponent(session.operator),
    'X-Operator-Role': encodeURIComponent(session.role),
    ...(init?.headers as Record<string, string> | undefined),
  }
  return fetch(url, { ...init, headers }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

export interface ActionResult {
  ok: boolean
  message: string
  entry?: Record<string, unknown> | null
}

/** 提交写操作：越权（403）与业务拦截（ok=false）都抛出后端原话，不再静默成功。 */
export async function submit(path: string, values: Record<string, unknown>): Promise<ActionResult> {
  const response = await request(path, { method: 'POST', body: JSON.stringify({ values }) })
  const payload = (await response.json().catch(() => null)) as
    | (ActionResult & { detail?: string })
    | null
  if (!response.ok) {
    throw new Error(payload?.detail ?? `接口返回 ${response.status}，操作未生效`)
  }
  if (payload && payload.ok === false) {
    throw new Error(payload.message || '操作未生效')
  }
  return payload ?? { ok: true, message: '操作已提交' }
}
