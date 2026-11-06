import { apiClient } from './http'
import type { SearchRequest, SearchResponse } from '../types/api'

export const searchApi = {
  /** 执行 BM25 与向量混合检索 */
  search(knowledgeBaseId: number, payload: SearchRequest) {
    return apiClient.post<SearchResponse>(
      `/knowledge-bases/${knowledgeBaseId}/search`,
      payload,
    )
  },
}