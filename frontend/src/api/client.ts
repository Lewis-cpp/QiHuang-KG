import { onBeforeUnmount, ref, shallowRef, type Ref } from 'vue'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

// spec §2.3: pin every request to the batch of the first response; a 409 means the server moved on.
const BUILD_KEY = 'qihuang.build_id'
let memoryBuild: string | null = null
export const snapshotChanged = ref(false)

export function storedBuild(): string | null {
  try { return sessionStorage.getItem(BUILD_KEY) ?? memoryBuild } catch { return memoryBuild }
}

export function rememberBuild(id: string) {
  memoryBuild = id
  try { sessionStorage.setItem(BUILD_KEY, id) } catch { /* memory only */ }
}

// A response from another batch than the pinned one is a snapshot change, even when it raced the pinning request.
function reconcileBuild(id: string) {
  const stored = storedBuild()
  if (!stored) rememberBuild(id)
  else if (stored !== id) {
    snapshotChanged.value = true
    throw new ApiError(409, 'snapshot_changed', '数据批次已更新，请刷新后重试')
  }
}

export function forgetBuild() {
  memoryBuild = null
  try { sessionStorage.removeItem(BUILD_KEY) } catch { /* memory only */ }
}

type Params = Record<string, string | number | string[] | undefined | null>
interface Options { signal?: AbortSignal; pinBuild?: boolean; acceptStatus?: number[] }

export async function get<T>(path: string, params: Params = {}, options: Options = {}): Promise<T> {
  const { signal, pinBuild = true, acceptStatus = [] } = options
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    // Arrays repeat the key (relation=A&relation=B), matching FastAPI list parameters.
    if (Array.isArray(value)) value.forEach(item => search.append(key, item))
    else if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const build = pinBuild ? storedBuild() : null
  if (build) search.set('build_id', build)
  const query = search.toString()
  let response: Response
  try {
    response = await fetch(`/api/v1${path}${query ? `?${query}` : ''}`, { signal, headers: { Accept: 'application/json' } })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(0, 'network_error', '无法连接服务，请检查后端是否启动。')
  }
  let body: any = null
  try { body = await response.json() } catch { /* non-JSON body */ }
  if (!response.ok && !acceptStatus.includes(response.status)) {
    // A gateway or dev proxy answers for a backend that is down without our error body.
    if (!body?.error && response.status >= 500) throw new ApiError(0, 'network_error', '无法连接服务，请检查后端是否启动。')
    const code = body?.error?.code ?? `http_${response.status}`
    const message = body?.error?.message ?? `请求未完成（HTTP ${response.status}），请稍后重试。`
    if (code === 'snapshot_changed') snapshotChanged.value = true
    throw new ApiError(response.status, code, message)
  }
  if (typeof body?.build_id === 'string') reconcileBuild(body.build_id)
  return body as T
}

export type ErrorKind = 'not_found' | 'unavailable' | 'snapshot' | 'error'

export function errorKind(error: ApiError, invalidIsNotFound = false): ErrorKind {
  if (error.status === 404 || (invalidIsNotFound && error.status === 422)) return 'not_found'
  if (error.status === 0 || error.status === 503) return 'unavailable'
  if (error.status === 409) return 'snapshot'
  return 'error'
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error
  return new ApiError(500, 'client_error', '页面处理数据时出错，请刷新后重试。')
}

// Keeps only the latest request's result and cancels the rest, including on unmount.
export function useLoader<T>(fn: (signal: AbortSignal) => Promise<T>) {
  const data = shallowRef<T | null>(null) as Ref<T | null>
  const error = shallowRef<ApiError | null>(null)
  const loading = ref(false)
  let controller: AbortController | undefined
  async function load() {
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true
    error.value = null
    try {
      const result = await fn(current.signal)
      if (controller === current) data.value = result
    } catch (e) {
      if (current.signal.aborted) return
      error.value = toApiError(e)
      data.value = null
    } finally {
      if (controller === current) loading.value = false
    }
  }
  function cancel() {
    controller?.abort()
    loading.value = false
  }
  onBeforeUnmount(() => controller?.abort())
  return { data, error, loading, load, cancel }
}
