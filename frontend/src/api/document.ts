import { apiClient } from './http'
import type { DocumentUploadResponse } from '../types/api'

export const documentApi = {
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
