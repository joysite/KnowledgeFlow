import { apiClient } from './http'
import type {
  KnowledgeBase,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseListResponse,
  KnowledgeBaseUpdateRequest,
} from '../types/api'

export const knowledgeBaseApi = {
  /** 分页获取知识库 */
  list(offset = 0, limit = 20, keyword?: string) {
    return apiClient.get<KnowledgeBaseListResponse>('/knowledge-bases', {
      params: { offset, limit, keyword: keyword?.trim() || undefined },
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

  /** 更新知识库名称或描述 */
  update(knowledgeBaseId: number, payload: KnowledgeBaseUpdateRequest) {
    return apiClient.patch<KnowledgeBase>(
      `/knowledge-bases/${knowledgeBaseId}`,
      payload,
    )
  },

  /** 彻底删除知识库及其关联资源 */
  delete(knowledgeBaseId: number) {
    return apiClient.delete<void>(`/knowledge-bases/${knowledgeBaseId}`)
  },
}