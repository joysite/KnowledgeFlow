import axios, { type AxiosError } from 'axios'

/**
 * KnowledgeFlow 统一 HTTP 请求客户端。
 *
 * 开发环境通过 Vite 代理将 /api 转发到 FastAPI。
 */
export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: {
    Accept: 'application/json',
  },
})

/**
 * 将 Axios 或 FastAPI 异常转换为适合界面展示的错误信息。
 */
export function getApiErrorMessage(
  error: unknown,
  fallback = '请求失败，请稍后重试',
): string {
  if (!axios.isAxiosError(error)) {
    return error instanceof Error ? error.message : fallback
  }

  const axiosError = error as AxiosError<{
    detail?: string | { message?: string }
    message?: string
  }>

  const responseData = axiosError.response?.data

  if (typeof responseData?.detail === 'string') {
    return responseData.detail
  }

  if (
    responseData?.detail &&
    typeof responseData.detail === 'object' &&
    typeof responseData.detail.message === 'string'
  ) {
    return responseData.detail.message
  }

  if (typeof responseData?.message === 'string') {
    return responseData.message
  }

  if (axiosError.code === 'ECONNABORTED') {
    return '请求超时，请检查服务状态'
  }

  if (!axiosError.response) {
    return '无法连接后端服务，请检查 FastAPI 是否启动'
  }

  return axiosError.message || fallback
}
