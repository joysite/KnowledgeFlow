import { apiClient } from './http'
import type { DocumentListResponse, DocumentUploadResponse } from '../types/api'

export const documentApi = {
  /** 分页获取指定知识库的文档 */
  list(knowledgeBaseId: number, offset = 0, limit = 20) {
    return apiClient.get<DocumentListResponse>(
      `/knowledge-bases/${knowledgeBaseId}/documents`,
      { params: { offset, limit } },
    )
  },

  /** 上传并导入文档 */
  upload(
    knowledgeBaseId: number,
    file: File,
    onProgress?: (progress: number) => void,
  ) {
    const formData = new FormData()
    formData.append('file', file)

    return apiClient.post<DocumentUploadResponse>(
      `/knowledge-bases/${knowledgeBaseId}/documents`,
      formData,
      {
        onUploadProgress(event) {
          if (event.total && event.total > 0) {
            const progress = Math.round((event.loaded / event.total) * 100)
            onProgress?.(Math.min(progress, 100))
          }
        },
      },
    )
  },
}
