/** 知识库信息 */
export interface KnowledgeBase {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string
}

/** 创建知识库请求 */
export interface KnowledgeBaseCreateRequest {
  name: string
  description?: string | null
}

/** 知识库分页响应 */
export interface KnowledgeBaseListResponse {
  items: KnowledgeBase[]
  offset: number
  limit: number
}

/** 文档上传响应 */
export interface DocumentUploadResponse {
  id: number
  knowledge_base_id: number
  name: string
  file_type: string
  file_size: number
  status: string
  created_at: string
}

/** 重复文档错误详情 */
export interface DocumentDuplicateResponse {
  code: number
  message: string
  document_id: number
}

/** 知识库检索请求 */
export interface SearchRequest {
  query: string
  top_k?: number
}

/** 混合检索结果 */
export interface SearchResultItem {
  chunk_id: number
  document_id: number
  document_name: string
  chunk_index: number
  content: string
  token_count: number
  vector_distance: number | null
  bm25_score: number | null
  rrf_score: number
}

/** 混合检索响应 */
export interface SearchResponse {
  knowledge_base_id: number
  query: string
  results: SearchResultItem[]
}

/** RAG 请求 */
export interface RAGRequest {
  query: string
  top_k?: number
}

/** RAG 来源 */
export interface RAGSourceItem {
  source_id: number
  chunk_id: number
  document_id: number
  document_name: string
  chunk_index: number
  content: string
  rrf_score: number
}

/** RAG 响应 */
export interface RAGResponse {
  knowledge_base_id: number
  query: string
  answer: string
  sources: RAGSourceItem[]
  retrieved_count: number
  context_token_count: number
}

/** Agent 请求 */
export interface AgentRequest {
  query: string
}

/** Agent 响应 */
export interface AgentResponse {
  knowledge_base_id: number
  query: string
  answer: string
  tool_calls_count: number
  iterations: number
}
