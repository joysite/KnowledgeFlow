<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { knowledgeBaseApi } from '../api/knowledgeBase'
import { documentApi } from '../api/document'
import { getApiErrorMessage } from '../api/http'
import type {
  KnowledgeBaseListItem,
  KnowledgeBaseCreateRequest,
  KnowledgeBaseUpdateRequest,
  DocumentListItem,
} from '../types/api'

const router = useRouter()
const items = ref<KnowledgeBaseListItem[]>([])
const keyword = ref('')
const appliedKeyword = ref('')
const offset = ref(0)
const pageSize = 20
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const saving = ref(false)
const deletingId = ref<number | null>(null)

const expandedIds = ref<number[]>([])
const documentsByKnowledgeBase = ref<Record<number, DocumentListItem[]>>({})
const documentTotals = ref<Record<number, number>>({})
const documentOffsets = ref<Record<number, number>>({})
const documentLoading = ref<Record<number, boolean>>({})
const documentErrors = ref<Record<number, string>>({})
const documentPageSize = 10

const showForm = ref(false)
const editingId = ref<number | null>(null)
const formName = ref('')
const formDescription = ref('')
const formError = ref('')

const pageNumber = computed(() => Math.floor(offset.value / pageSize) + 1)
const hasNextPage = computed(() => items.value.length === pageSize)

async function loadItems() {
  loading.value = true
  error.value = ''

  try {
    const response = await knowledgeBaseApi.list(
      offset.value,
      pageSize,
      appliedKeyword.value,
    )
    items.value = response.data.items
  } catch (err) {
    error.value = getApiErrorMessage(err, '获取知识库列表失败')
  } finally {
    loading.value = false
  }
}

async function search() {
  offset.value = 0
  appliedKeyword.value = keyword.value.trim()
  await loadItems()
}

async function changePage(direction: -1 | 1) {
  offset.value = Math.max(0, offset.value + direction * pageSize)
  await loadItems()
}

function openCreateForm() {
  editingId.value = null
  formName.value = ''
  formDescription.value = ''
  formError.value = ''
  showForm.value = true
}

function openEditForm(item: KnowledgeBaseListItem) {
  editingId.value = item.id
  formName.value = item.name
  formDescription.value = item.description || ''
  formError.value = ''
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  formError.value = ''
}

async function saveKnowledgeBase() {
  const name = formName.value.trim()

  if (!name) {
    formError.value = '请输入知识库名称'
    return
  }

  saving.value = true
  formError.value = ''

  try {
    const description = formDescription.value.trim() || null

    if (editingId.value === null) {
      const payload: KnowledgeBaseCreateRequest = { name, description }
      await knowledgeBaseApi.create(payload)
      offset.value = 0
    } else {
      const payload: KnowledgeBaseUpdateRequest = { name, description }
      await knowledgeBaseApi.update(editingId.value, payload)
    }

    closeForm()
    await loadItems()
  } catch (err) {
    formError.value = getApiErrorMessage(err, '保存知识库失败')
  } finally {
    saving.value = false
  }
}

async function deleteKnowledgeBase(item: KnowledgeBaseListItem) {
  if (deletingId.value !== null) {
    return
  }

  if (
    item.status !== 'deleting' &&
    !window.confirm(
      `确定彻底删除知识库「${item.name}」吗？关联文档、分块、向量索引和上传文件也会被删除。`,
    )
  ) {
    return
  }

  deletingId.value = item.id
  actionError.value = ''

  try {
    await knowledgeBaseApi.delete(item.id)

    if (items.value.length === 1 && offset.value > 0) {
      offset.value = Math.max(0, offset.value - pageSize)
    }

    await loadItems()
  } catch (err) {
    actionError.value = getApiErrorMessage(err, '删除知识库失败')
    await loadItems()
  } finally {
    deletingId.value = null
  }
}

async function loadDocuments(
  knowledgeBaseId: number,
  requestedOffset = documentOffsets.value[knowledgeBaseId] ?? 0,
) {
  documentLoading.value = {
    ...documentLoading.value,
    [knowledgeBaseId]: true,
  }
  documentErrors.value = {
    ...documentErrors.value,
    [knowledgeBaseId]: '',
  }

  try {
    const response = await documentApi.list(
      knowledgeBaseId,
      requestedOffset,
      documentPageSize,
    )
    documentsByKnowledgeBase.value = {
      ...documentsByKnowledgeBase.value,
      [knowledgeBaseId]: response.data.items,
    }
    documentTotals.value = {
      ...documentTotals.value,
      [knowledgeBaseId]: response.data.total,
    }
    documentOffsets.value = {
      ...documentOffsets.value,
      [knowledgeBaseId]: response.data.offset,
    }
  } catch (err) {
    documentErrors.value = {
      ...documentErrors.value,
      [knowledgeBaseId]: getApiErrorMessage(err, '获取文档列表失败'),
    }
  } finally {
    documentLoading.value = {
      ...documentLoading.value,
      [knowledgeBaseId]: false,
    }
  }
}

async function toggleDocuments(knowledgeBaseId: number) {
  if (expandedIds.value.includes(knowledgeBaseId)) {
    expandedIds.value = expandedIds.value.filter(
      (id) => id !== knowledgeBaseId,
    )
    return
  }

  expandedIds.value = [...expandedIds.value, knowledgeBaseId]

  if (!documentsByKnowledgeBase.value[knowledgeBaseId]) {
    await loadDocuments(knowledgeBaseId, 0)
  }
}

async function changeDocumentPage(
  knowledgeBaseId: number,
  direction: -1 | 1,
) {
  const currentOffset = documentOffsets.value[knowledgeBaseId] ?? 0
  const nextOffset = Math.max(
    0,
    currentOffset + direction * documentPageSize,
  )
  await loadDocuments(knowledgeBaseId, nextOffset)
}

function documentPageNumber(knowledgeBaseId: number) {
  return Math.floor(
    (documentOffsets.value[knowledgeBaseId] ?? 0) / documentPageSize,
  ) + 1
}

function hasNextDocumentPage(knowledgeBaseId: number) {
  const offset = documentOffsets.value[knowledgeBaseId] ?? 0
  const total = documentTotals.value[knowledgeBaseId] ?? 0
  const currentItems = documentsByKnowledgeBase.value[knowledgeBaseId] ?? []

  return offset + currentItems.length < total
}

function documentStatusLabel(status: DocumentListItem['status']) {
  const labels: Record<DocumentListItem['status'], string> = {
    pending: '等待处理',
    processing: '处理中',
    completed: '已完成',
    failed: '导入失败',
  }
  return labels[status]
}

function openKnowledgeBase(id: number) {
  router.push(`/knowledge-bases/${id}`)
}

function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

onMounted(loadItems)
</script>

<template>
  <div class="admin-page">
    <header class="topbar">
      <RouterLink to="/" class="brand">
        <img
          class="brand-logo"
          src="/knowledgeflow-logo.png"
          alt="KnowledgeFlow"
        />
        <span>KnowledgeFlow</span>
      </RouterLink>

      <div class="admin-topbar-right">
        <span class="admin-label">管理后台</span>
        <RouterLink to="/" class="back-link">返回工作台 ↗</RouterLink>
      </div>
    </header>

    <main class="admin-main">
      <section class="admin-heading">
        <div>
          <div class="eyebrow">KNOWLEDGE MANAGEMENT</div>
          <h1>知识库管理</h1>
          <p>统一管理知识空间，查看资源规模并维护知识库生命周期。</p>
        </div>

        <button class="primary-button" type="button" @click="openCreateForm">
          <span class="button-icon">＋</span>
          创建知识库
        </button>
      </section>

      <section class="admin-toolbar">
        <form class="admin-search" @submit.prevent="search">
          <input
            v-model="keyword"
            type="search"
            maxlength="128"
            placeholder="搜索知识库名称…"
            aria-label="搜索知识库名称"
          />
          <button class="primary-button" type="submit" :disabled="loading">
            搜索
          </button>
        </form>

        <button
          class="secondary-button"
          type="button"
          :disabled="loading"
          @click="loadItems"
        >
          {{ loading ? '加载中…' : '↻ 刷新列表' }}
        </button>
      </section>

      <section v-if="showForm" class="admin-form-panel">
        <div class="panel-heading">
          <div>
            <h2>{{ editingId === null ? '创建知识库' : '编辑知识库' }}</h2>
            <p>设置知识库名称和描述信息。</p>
          </div>
          <button
            class="icon-button"
            type="button"
            aria-label="关闭表单"
            @click="closeForm"
          >
            ×
          </button>
        </div>

        <form class="admin-form" @submit.prevent="saveKnowledgeBase">
          <label for="admin-kb-name">知识库名称 <span>*</span></label>
          <input
            id="admin-kb-name"
            v-model="formName"
            type="text"
            maxlength="128"
            placeholder="请输入知识库名称"
            required
          />

          <label for="admin-kb-description">描述</label>
          <textarea
            id="admin-kb-description"
            v-model="formDescription"
            rows="3"
            placeholder="介绍知识库的用途（选填）"
          ></textarea>

          <p v-if="formError" class="error-message">{{ formError }}</p>

          <div class="form-actions">
            <button
              class="secondary-button"
              type="button"
              @click="closeForm"
            >
              取消
            </button>
            <button class="primary-button" type="submit" :disabled="saving">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </form>
      </section>

      <p v-if="actionError" class="admin-alert">
        {{ actionError }}
      </p>

      <section class="admin-list-panel">
        <div class="admin-list-heading">
          <div>
            <h2>知识库列表</h2>
            <p>
              {{ appliedKeyword ? `名称包含“${appliedKeyword}”` : '管理当前本地知识空间' }}
            </p>
          </div>
          <span class="result-count">本页 {{ items.length }} 个</span>
        </div>

        <div v-if="loading && items.length === 0" class="admin-state">
          <div class="loading-spinner"></div>
          <p>正在加载知识库…</p>
        </div>

        <div v-else-if="error" class="admin-state">
          <div class="state-icon error-icon">!</div>
          <h3>加载失败</h3>
          <p>{{ error }}</p>
          <button class="secondary-button" type="button" @click="loadItems">
            重新加载
          </button>
        </div>

        <div v-else-if="items.length === 0" class="admin-state">
          <div class="empty-icon">▤</div>
          <h3>{{ appliedKeyword ? '没有找到匹配的知识库' : '还没有知识库' }}</h3>
          <p>
            {{ appliedKeyword ? '试试其他关键词。' : '创建一个知识库，开始整理你的知识资源。' }}
          </p>
          <button
            v-if="!appliedKeyword"
            class="primary-button"
            type="button"
            @click="openCreateForm"
          >
            ＋ 创建知识库
          </button>
        </div>

        <div v-else class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>知识库</th>
                <th>文档数量</th>
                <th>创建时间</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="item in items" :key="item.id">
              <tr>
                <td class="admin-name-cell">
                  <div class="admin-name-line">
                    <span class="knowledge-icon">▤</span>
                    <div>
                      <strong>{{ item.name }}</strong>
                      <span class="admin-description">
                        {{ item.description || '暂无描述' }}
                      </span>
                      <span class="admin-id">ID: {{ item.id }}</span>
                    </div>
                  </div>
                  <p v-if="item.deletion_error" class="deletion-error">
                    删除失败：{{ item.deletion_error }}
                  </p>
                </td>
                <td>{{ item.document_count }}</td>
                <td class="date-cell">{{ formatDate(item.created_at) }}</td>
                <td>
                  <span
                    class="status-pill"
                    :class="item.status === 'deleting' ? 'status-deleting' : 'status-active'"
                  >
                    {{ item.status === 'deleting' ? '删除待重试' : '正常' }}
                  </span>
                </td>
                <td>
                  <div class="admin-actions">
                    <button
                      class="text-button"
                      type="button"
                      @click="openKnowledgeBase(item.id)"
                    >
                      详情
                    </button>
                    <button
                      class="text-button"
                      type="button"
                      :aria-expanded="expandedIds.includes(item.id)"
                      @click="toggleDocuments(item.id)"
                    >
                      {{ expandedIds.includes(item.id) ? '收起文档' : '文档' }}
                    </button>
                    <button
                      v-if="item.status === 'active'"
                      class="text-button"
                      type="button"
                      @click="openEditForm(item)"
                    >
                      编辑
                    </button>
                    <button
                      class="text-button danger-text"
                      type="button"
                      :disabled="deletingId !== null"
                      @click="deleteKnowledgeBase(item)"
                    >
                      {{
                        deletingId === item.id
                          ? '处理中…'
                          : item.status === 'deleting'
                            ? '重试删除'
                            : '删除'
                      }}
                    </button>
                  </div>
                </td>
              </tr>
              <tr
                v-if="expandedIds.includes(item.id)"
                class="document-detail-row"
              >
                <td colspan="5">
                  <section class="document-list-panel">
                    <div class="document-list-heading">
                      <strong>文档列表</strong>
                      <span>
                        共 {{ documentTotals[item.id] ?? 0 }} 个文档
                      </span>
                    </div>

                    <div v-if="documentLoading[item.id]" class="document-state">
                      正在加载文档…
                    </div>

                    <div v-else-if="documentErrors[item.id]" class="document-state document-error">
                      <span>{{ documentErrors[item.id] }}</span>
                      <button
                        class="text-button"
                        type="button"
                        @click="loadDocuments(item.id)"
                      >
                        重试
                      </button>
                    </div>

                    <div
                      v-else-if="(documentsByKnowledgeBase[item.id] ?? []).length === 0"
                      class="document-state"
                    >
                      这个知识库还没有文档。
                    </div>

                    <div v-else class="admin-table-wrap">
                      <table class="document-table">
                        <thead>
                          <tr>
                            <th>文档名称</th>
                            <th>类型</th>
                            <th>状态</th>
                            <th>分块数量</th>
                            <th>创建时间</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr
                            v-for="document in documentsByKnowledgeBase[item.id]"
                            :key="document.id"
                          >
                            <td>
                              <div class="document-name">{{ document.name }}</div>
                              <div
                                v-if="document.error_message"
                                class="document-error-message"
                              >
                                {{ document.error_message }}
                              </div>
                            </td>
                            <td>{{ document.file_type.toUpperCase() }}</td>
                            <td>
                              <span
                                class="status-pill"
                                :class="`document-status-${document.status}`"
                              >
                                {{ documentStatusLabel(document.status) }}
                              </span>
                            </td>
                            <td>{{ document.chunk_count }}</td>
                            <td class="date-cell">
                              {{ formatDate(document.created_at) }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>

                    <div
                      v-if="(documentTotals[item.id] ?? 0) > documentPageSize"
                      class="document-pagination"
                    >
                      <span>
                        第 {{ documentPageNumber(item.id) }} 页
                      </span>
                      <div>
                        <button
                          class="secondary-button"
                          type="button"
                          :disabled="(documentOffsets[item.id] ?? 0) === 0 || documentLoading[item.id]"
                          @click="changeDocumentPage(item.id, -1)"
                        >
                          上一页
                        </button>
                        <button
                          class="secondary-button"
                          type="button"
                          :disabled="!hasNextDocumentPage(item.id) || documentLoading[item.id]"
                          @click="changeDocumentPage(item.id, 1)"
                        >
                          下一页
                        </button>
                      </div>
                    </div>
                  </section>
                </td>
              </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div v-if="items.length > 0" class="admin-pagination">
          <span>第 {{ pageNumber }} 页</span>
          <div>
            <button
              class="secondary-button"
              type="button"
              :disabled="offset === 0 || loading"
              @click="changePage(-1)"
            >
              上一页
            </button>
            <button
              class="secondary-button"
              type="button"
              :disabled="!hasNextPage || loading"
              @click="changePage(1)"
            >
              下一页
            </button>
          </div>
        </div>
      </section>
    </main>

    <footer class="footer">
      <span>KnowledgeFlow</span>
      <span>本地优先的智能知识库系统</span>
    </footer>
  </div>
</template>

<style scoped>
.admin-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f7f8fc;
}

.admin-topbar-right {
  display: flex;
  align-items: center;
  gap: 22px;
}

.admin-label {
  color: #77758e;
  font-size: 13px;
}

.back-link {
  color: var(--primary);
  font-size: 13px;
  font-weight: 600;
}

.admin-main {
  width: min(1200px, 88%);
  margin: 0 auto;
  flex: 1;
  padding: 54px 0 70px;
}

.admin-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.admin-heading h1 {
  margin: 0;
  color: var(--text);
  font-size: clamp(28px, 4vw, 36px);
  letter-spacing: -1px;
}

.admin-heading p,
.admin-list-heading p {
  margin-top: 10px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.admin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 34px;
  padding: 17px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
}

.admin-search {
  display: flex;
  flex: 1;
  gap: 10px;
}

.admin-search input,
.admin-form input,
.admin-form textarea {
  width: 100%;
  min-width: 0;
  padding: 11px 13px;
  border: 1px solid #e5e6ee;
  border-radius: 8px;
  outline: none;
  color: var(--text);
  background: #fff;
  font-size: 13px;
}

.admin-search input:focus,
.admin-form input:focus,
.admin-form textarea:focus {
  border-color: #9186e6;
  box-shadow: 0 0 0 3px rgba(101, 88, 211, 0.09);
}

.admin-form-panel,
.admin-list-panel {
  margin-top: 24px;
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 5px 20px rgba(37, 36, 58, 0.035);
}

.admin-form {
  display: flex;
  flex-direction: column;
  margin-top: 18px;
}

.admin-form label {
  margin: 15px 0 8px;
  color: #44445a;
  font-size: 13px;
  font-weight: 600;
}

.admin-form label span {
  color: #e35d72;
}

.admin-form textarea {
  resize: vertical;
}

.admin-list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.admin-list-heading h2 {
  margin: 0;
  color: var(--text);
  font-size: 18px;
}

.result-count {
  color: var(--muted);
  font-size: 12px;
}

.admin-table-wrap {
  overflow-x: auto;
}

.admin-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.admin-table th {
  padding: 13px 12px;
  color: #85869a;
  background: #fafafe;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.admin-table td {
  padding: 17px 12px;
  border-bottom: 1px solid #f0f0f5;
  color: #55566c;
  vertical-align: middle;
}

.admin-table tbody tr:last-child td {
  border-bottom: 0;
}

.admin-name-cell {
  min-width: 250px;
}

.admin-name-line {
  display: flex;
  align-items: center;
  gap: 12px;
}

.admin-name-line strong,
.admin-description,
.admin-id {
  display: block;
}

.admin-name-line strong {
  color: var(--text);
  font-size: 13px;
}

.admin-description {
  max-width: 300px;
  margin-top: 5px;
  overflow: hidden;
  color: var(--muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.admin-id {
  margin-top: 5px;
  color: #a0a0ae;
  font-size: 10px;
}

.date-cell {
  min-width: 145px;
  white-space: nowrap;
  font-size: 12px;
}

.status-pill {
  display: inline-flex;
  padding: 5px 9px;
  border-radius: 20px;
  font-size: 11px;
  white-space: nowrap;
}

.status-active {
  color: #248b68;
  background: #e9f8f1;
}

.status-deleting {
  color: #b87820;
  background: #fff4df;
}

.admin-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
}

.text-button {
  padding: 4px 0;
  border: 0;
  color: var(--primary);
  background: transparent;
  font-size: 12px;
  font-weight: 600;
}

.text-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.danger-text {
  color: #d94c61;
}

.deletion-error {
  margin: 10px 0 0 51px;
  color: #c44d5d;
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.admin-state {
  min-height: 245px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.admin-state h3 {
  margin: 16px 0 7px;
  color: var(--text);
  font-size: 15px;
}

.admin-state p {
  margin: 0 0 16px;
  color: var(--muted);
  font-size: 13px;
}

.admin-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 22px;
  color: var(--muted);
  font-size: 12px;
}

.admin-pagination > div {
  display: flex;
  gap: 9px;
}

.admin-alert {
  margin: 18px 0 0;
  padding: 12px 15px;
  border: 1px solid #f2d4d8;
  border-radius: 9px;
  color: #c44d5d;
  background: #fff6f7;
  font-size: 12px;
  line-height: 1.6;
}

@media (max-width: 760px) {
  .admin-main {
    width: 90%;
    padding: 38px 0 48px;
  }

  .admin-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .admin-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .admin-list-panel,
  .admin-form-panel {
    padding: 17px;
  }

  .admin-topbar-right {
    gap: 10px;
  }
}

@media (max-width: 480px) {
  .admin-label {
    display: none;
  }

  .admin-search {
    flex-direction: column;
  }

  .admin-pagination {
    align-items: flex-start;
    flex-direction: column;
    gap: 12px;
  }
}

.document-detail-row > td {
  padding: 0 !important;
  background: #fafafe;
}

.document-list-panel {
  padding: 18px 20px 20px;
  border-top: 1px solid var(--border);
}

.document-list-heading,
.document-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.document-list-heading {
  margin-bottom: 12px;
  color: var(--text);
  font-size: 12px;
}

.document-list-heading span,
.document-pagination {
  color: var(--muted);
  font-size: 11px;
}

.document-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 12px;
}

.document-table th {
  padding: 10px;
  color: #85869a;
  background: #f3f3fa;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.document-table td {
  padding: 11px 10px;
  border-bottom: 1px solid #ededf3;
  color: #55566c;
  vertical-align: middle;
}

.document-name {
  color: var(--text);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.document-error-message {
  max-width: 420px;
  margin-top: 5px;
  color: #c44d5d;
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.document-state {
  padding: 22px 10px;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

.document-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #c44d5d;
}

.document-pagination {
  margin-top: 14px;
}

.document-pagination > div {
  display: flex;
  gap: 8px;
}

.document-status-pending {
  color: #8a6b20;
  background: #fff6df;
}

.document-status-processing {
  color: #3769b1;
  background: #eaf2ff;
}

.document-status-completed {
  color: #248b68;
  background: #e9f8f1;
}

.document-status-failed {
  color: #c44d5d;
  background: #fff0f1;
}

</style>
