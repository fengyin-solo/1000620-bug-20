/** 统一请求封装：拼后端地址、带操作角色头、抛网络错误、给页脚留一句可读的说明。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const session = useSessionStore()
  // 请求头只允许 ASCII，中文角色名按 URL 百分号编码传输，后端统一解码
  return fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Operator-Role': encodeURIComponent(session.role),
      'X-Operator-Name': encodeURIComponent(session.operator),
      ...init?.headers,
    },
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

/** 从失败响应里取出可读原因：优先后端的 detail（403/404），其次 ActionResult 的 message。 */
export async function responseError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string' && body.detail) {
      return body.detail
    }
    if (typeof body?.message === 'string' && body.message) {
      return body.message
    }
  } catch {
    // 响应体不是 JSON 时走兜底文案
  }
  return `${fallback}（接口返回 ${response.status}）`
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(await responseError(response, '数据未更新'))
  }
  return (await response.json()) as T
}
