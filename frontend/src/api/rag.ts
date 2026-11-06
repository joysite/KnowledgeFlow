import { apiClient } from './http'
import type { RAGRequest, RAGResponse } from '../types/api'

export const ragApi = {
  /** 基于知识库生成回答 */
  ask(knowledgeBaseId: number, payload: RAGRequest) {
    return apiClient.post<RAGResponse>(
      `/knowledge-bases/${knowledgeBaseId}/rag`,
      payload,
      {
        timeout: 180_000,
      },
    )
  },
}
