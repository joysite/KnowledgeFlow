import { apiClient } from './http'
import type { AgentRequest, AgentResponse } from '../types/api'

export const agentApi = {
  /** 调用 Agent 执行智能问答 */
  ask(knowledgeBaseId: number, payload: AgentRequest) {
    return apiClient.post<AgentResponse>(
      `/knowledge-bases/${knowledgeBaseId}/agent`,
      payload,
    )
  },
}