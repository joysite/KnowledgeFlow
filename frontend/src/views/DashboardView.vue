<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useKnowledgeBaseStore } from '../stores/knowledgeBase'

const router = useRouter()
const store = useKnowledgeBaseStore()

const showCreateForm = ref(false)
const creating = ref(false)
const createError = ref('')
const name = ref('')
const description = ref('')
const offset = ref(0)
const pageSize = 20

const hasNextPage = computed(() => store.items.length === pageSize)

async function loadKnowledgeBases() {
  try {
    await store.fetchKnowledgeBases(offset.value, pageSize)
  } catch {
    // 错误信息由 Store 统一维护
  }
}

async function createKnowledgeBase() {
  const trimmedName = name.value.trim()

  if (!trimmedName) {
    createError.value = '请输入知识库名称'
    return
  }

  creating.value = true
  createError.value = ''

  try {
    const knowledgeBase = await store.createKnowledgeBase({
      name: trimmedName,
      description: description.value.trim() || null,
    })

    showCreateForm.value = false
    name.value = ''
    description.value = ''
    offset.value = 0

    await loadKnowledgeBases()
    await router.push(`/knowledge-bases/${knowledgeBase.id}`)
  } catch {
    createError.value = store.error || '创建知识库失败'
  } finally {
    creating.value = false
  }
}

function openKnowledgeBase(id: number) {
  router.push(`/knowledge-bases/${id}`)
}

async function changePage(direction: -1 | 1) {
  offset.value = Math.max(0, offset.value + direction * pageSize)
  await loadKnowledgeBases()
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

onMounted(loadKnowledgeBases)
</script>

<template>
  <div class="dashboard">
    <header class="topbar">
      <RouterLink to="/" class="brand">
        <img class="brand-logo" src="/knowledgeflow-logo.png" alt="KnowledgeFlow" />
        <span>KnowledgeFlow</span>
      </RouterLink>

      <div class="topbar-right">
        <span class="system-status">
          <span class="status-dot"></span>
          本地知识库
        </span>
      </div>
    </header>

    <main class="main-content">
      <section class="welcome-section">
        <div>
          <div class="eyebrow">KNOWLEDGE WORKSPACE</div>
          <h1>知识库工作台</h1>
          <p class="welcome-description">
            集中管理你的知识资源，使用混合检索、RAG 和 Agent 探索知识。
          </p>
        </div>

        <button
          class="primary-button"
          type="button"
          @click="showCreateForm = !showCreateForm"
        >
          <span class="button-icon">＋</span>
          创建知识库
        </button>
      </section>

      <section v-if="showCreateForm" class="create-panel">
        <div class="panel-heading">
          <div>
            <h2>创建知识库</h2>
            <p>为新的知识空间设置名称和描述。</p>
          </div>
          <button
            class="icon-button"
            type="button"
            aria-label="关闭"
            @click="showCreateForm = false"
          >
            ×
          </button>
        </div>

        <form class="create-form" @submit.prevent="createKnowledgeBase">
          <label for="kb-name">知识库名称 <span>*</span></label>
          <input
            id="kb-name"
            v-model="name"
            type="text"
            maxlength="128"
            placeholder="例如：人工智能技术资料"
            required
          />

          <label for="kb-description">描述</label>
          <textarea
            id="kb-description"
            v-model="description"
            rows="3"
            placeholder="简单介绍这个知识库的用途（选填）"
          ></textarea>

          <p v-if="createError" class="error-message">{{ createError }}</p>

          <div class="form-actions">
            <button
              class="secondary-button"
              type="button"
              @click="showCreateForm = false"
            >
              取消
            </button>
            <button class="primary-button" type="submit" :disabled="creating">
              {{ creating ? '创建中…' : '确认创建' }}
            </button>
          </div>
        </form>
      </section>

      <section class="stats-row">
        <div class="stat-card">
          <div class="stat-icon purple">▤</div>
          <div>
            <div class="stat-label">当前页知识库</div>
            <div class="stat-value">{{ store.items.length }}</div>
          </div>
        </div>

        <div class="stat-card">
          <div class="stat-icon green">⌘</div>
          <div>
            <div class="stat-label">知识管理模式</div>
            <div class="stat-description">本地优先 · 私有数据</div>
          </div>
        </div>
      </section>

      <section class="library-section">
        <div class="section-heading">
          <div>
            <h2>我的知识库</h2>
            <p>选择一个知识库，开始管理文档和探索知识。</p>
          </div>

          <button
            class="refresh-button"
            type="button"
            :disabled="store.loading"
            @click="loadKnowledgeBases"
          >
            <span :class="{ spinning: store.loading }">↻</span>
            刷新
          </button>
        </div>

        <div v-if="store.loading && store.items.length === 0" class="state-card">
          <div class="loading-spinner"></div>
          <p>正在加载知识库…</p>
        </div>

        <div v-else-if="store.error" class="state-card">
          <div class="state-icon error-icon">!</div>
          <h3>加载失败</h3>
          <p>{{ store.error }}</p>
          <button class="secondary-button" type="button" @click="loadKnowledgeBases">
            重新加载
          </button>
        </div>

        <div v-else-if="store.items.length === 0" class="empty-state">
          <div class="empty-icon">▤</div>
          <h3>还没有知识库</h3>
          <p>创建第一个知识库，开始构建你的个人知识空间。</p>
          <button
            class="primary-button"
            type="button"
            @click="showCreateForm = true"
          >
            ＋ 创建第一个知识库
          </button>
        </div>

        <div v-else class="knowledge-grid">
          <button
            v-for="item in store.items"
            :key="item.id"
            class="knowledge-card"
            type="button"
            @click="openKnowledgeBase(item.id)"
          >
            <div class="card-top">
              <div class="knowledge-icon">▤</div>
              <span class="card-arrow">↗</span>
            </div>

            <h3>{{ item.name }}</h3>
            <p class="card-description">
              {{ item.description || '暂无描述' }}
            </p>

            <div class="card-footer">
              <span>知识库 #{{ item.id }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
          </button>
        </div>

        <div v-if="store.items.length > 0" class="pagination">
          <span>当前页：{{ Math.floor(offset / pageSize) + 1 }}</span>
          <div>
            <button
              class="secondary-button"
              type="button"
              :disabled="offset === 0 || store.loading"
              @click="changePage(-1)"
            >
              上一页
            </button>
            <button
              class="secondary-button"
              type="button"
              :disabled="!hasNextPage || store.loading"
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
