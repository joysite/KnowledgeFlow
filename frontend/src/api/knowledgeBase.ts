import { apiClient } from './http'
import type {
  KnowledgeBase,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseListResponse,
} from '../types/api'

export const knowledgeBaseApi = {
  /** 分页获取知识库 */
  list(offset = 0, limit = 20) {
    return apiClient.get<KnowledgeBaseListResponse>('/knowledge-bases', {
      params: { offset, limit },
    })
  },

  /** 创建知识库 */
  create(payload: KnowledgeBaseCreateRequest) {
    return apiClient.post<KnowledgeBase>('/knowledge-bases', payload)
  },

  /** 获取知识库详情 */
  getById(knowledgeBaseId: number) {
    return apiClient.get<KnowledgeBase>(`/knowledge-bases/${knowledgeBaseId}`)
  },
}