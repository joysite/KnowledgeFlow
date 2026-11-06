import { defineStore } from 'pinia'
import { ref } from 'vue'
import { knowledgeBaseApi } from '../api/knowledgeBase'
import { getApiErrorMessage } from '../api/http'
import type {
  KnowledgeBase,
  KnowledgeBaseCreateRequest,
} from '../types/api'

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  const items = ref<KnowledgeBase[]>([])
  const current = ref<KnowledgeBase | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** 获取知识库列表 */
  async function fetchKnowledgeBases(offset = 0, limit = 20) {
    loading.value = true
    error.value = null

    try {
      const response = await knowledgeBaseApi.list(offset, limit)
      items.value = response.data.items
      return response.data
    } catch (err) {
      error.value = getApiErrorMessage(err, '获取知识库列表失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  /** 创建知识库 */
  async function createKnowledgeBase(payload: KnowledgeBaseCreateRequest) {
    error.value = null

    try {
      const response = await knowledgeBaseApi.create(payload)
      items.value = [...items.value, response.data]
      current.value = response.data
      return response.data
    } catch (err) {
      error.value = getApiErrorMessage(err, '创建知识库失败')
      throw err
    }
  }

  /** 选择知识库并加载详情 */
  async function selectKnowledgeBase(knowledgeBaseId: number) {
    loading.value = true
    error.value = null

    try {
      const response = await knowledgeBaseApi.getById(knowledgeBaseId)
      current.value = response.data
      return response.data
    } catch (err) {
      error.value = getApiErrorMessage(err, '获取知识库详情失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  function clearCurrent() {
    current.value = null
    error.value = null
  }

  return {
    items,
    current,
    loading,
    error,
    fetchKnowledgeBases,
    createKnowledgeBase,
    selectKnowledgeBase,
    clearCurrent,
  }
})
