<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useKnowledgeBaseStore } from '../stores/knowledgeBase'
import DocumentUploadPanel from '../components/DocumentUploadPanel.vue'
import DocumentSearchPanel from '../components/DocumentSearchPanel.vue'
import RAGChatPanel from '../components/RAGChatPanel.vue'
import AgentChatPanel from '../components/AgentChatPanel.vue'

type WorkspaceTab = 'overview' | 'documents' | 'search' | 'rag' | 'agent'

const route = useRoute()
const store = useKnowledgeBaseStore()
const activeTab = ref<WorkspaceTab>('overview')

const tabs: { id: WorkspaceTab; label: string; icon: string }[] = [
  { id: 'overview', label: '概览', icon: '▦' },
  { id: 'documents', label: '文档管理', icon: '▤' },
  { id: 'search', label: '混合检索', icon: '⌕' },
  { id: 'rag', label: 'RAG 问答', icon: '✧' },
  { id: 'agent', label: 'Agent 助手', icon: '⌘' },
]

const routeDescriptions: Record<WorkspaceTab, string> = {
  overview: '查看知识库信息，快速进入各项功能。',
  documents: '上传本地文档，将文件导入知识库并建立索引。',
  search: '通过 BM25 与向量检索联合查找知识库内容。',
  rag: '结合检索内容生成回答，并查看引用来源。',
  agent: '由 Agent 自主判断任务并调用知识库工具。',
}

const knowledgeBaseId = computed(() => {
  const value = Number(route.params.id)
  return Number.isSafeInteger(value) && value > 0 ? value : null
})

const formattedCreatedAt = computed(() => {
  const value = store.current?.created_at

  if (!value) {
    return '-'
  }

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
})

function switchTab(tab: WorkspaceTab) {
  activeTab.value = tab
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

watch(
  knowledgeBaseId,
  async (id) => {
    activeTab.value = 'overview'
    store.clearCurrent()

    if (id === null) {
      store.error = '无效的知识库 ID'
      return
    }

    try {
      await store.selectKnowledgeBase(id)
    } catch {
      // 错误信息由 Store 统一维护
    }
  },
  { immediate: true },
)
</script>

<template>
  <div class="knowledge-page">
    <header class="knowledge-topbar">
      <RouterLink to="/" class="knowledge-brand">
        <img class="brand-logo" src="/knowledgeflow-logo.png" alt="KnowledgeFlow" />
        <span>KnowledgeFlow</span>
      </RouterLink>

      <RouterLink to="/" class="back-link">
        <span>←</span>
        返回工作台
      </RouterLink>
    </header>

    <main class="knowledge-main">
      <div class="breadcrumb">
        <RouterLink to="/">知识库工作台</RouterLink>
        <span>/</span>
        <span>知识库详情</span>
        <template v-if="store.current">
          <span>/</span>
          <span class="breadcrumb-current">{{ store.current.name }}</span>
        </template>
      </div>

      <section v-if="store.loading" class="detail-state">
        <div class="loading-spinner"></div>
        <p>正在加载知识库信息…</p>
      </section>

      <section v-else-if="store.error" class="detail-state">
        <div class="detail-error-icon">!</div>
        <h2>无法加载知识库</h2>
        <p>{{ store.error }}</p>
        <RouterLink to="/" class="detail-primary-button">
          返回知识库工作台
        </RouterLink>
      </section>

      <template v-else-if="store.current">
        <section class="knowledge-header">
          <div class="knowledge-heading-main">
            <div class="knowledge-large-icon">▤</div>
            <div class="knowledge-heading-text">
              <div class="knowledge-eyebrow">KNOWLEDGE BASE</div>
              <h1>{{ store.current.name }}</h1>
              <p>{{ store.current.description || '这个知识库暂时没有描述。' }}</p>
            </div>
          </div>

          <span class="knowledge-status">
            <span></span>
            正常运行
          </span>
        </section>

        <section class="workspace">
          <nav class="workspace-nav" aria-label="知识库功能导航">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              class="workspace-nav-item"
              :class="{ active: activeTab === tab.id }"
              :aria-current="activeTab === tab.id ? 'page' : undefined"
              @click="switchTab(tab.id)"
            >
              <span class="nav-icon">{{ tab.icon }}</span>
              {{ tab.label }}
            </button>
          </nav>

          <section class="workspace-content">
            <div class="workspace-heading">
              <div>
                <span class="workspace-eyebrow">WORKSPACE</span>
                <h2>{{ tabs.find((tab) => tab.id === activeTab)?.label }}</h2>
                <p>{{ routeDescriptions[activeTab] }}</p>
              </div>

              <span class="workspace-id">KB #{{ store.current.id }}</span>
            </div>

            <!-- 概览 -->
            <div v-show="activeTab === 'overview'" class="overview-content">
              <section class="overview-info">
                <div class="overview-info-heading">
                  <div>
                    <h3>知识库信息</h3>
                    <p>当前知识库的基本信息与运行状态。</p>
                  </div>
                  <span class="overview-status">
                    <span></span>
                    运行正常
                  </span>
                </div>

                <div class="overview-meta">
                  <div>
                    <span>知识库 ID</span>
                    <strong>#{{ store.current.id }}</strong>
                  </div>
                  <div>
                    <span>创建时间</span>
                    <strong>{{ formattedCreatedAt }}</strong>
                  </div>
                </div>
              </section>

              <section class="overview-functions">
                <div class="overview-section-heading">
                  <h3>功能工作区</h3>
                  <span>选择功能开始使用</span>
                </div>

                <div class="workspace-cards">
                  <button
                    type="button"
                    class="workspace-card"
                    @click="switchTab('documents')"
                  >
                    <span class="workspace-card-icon purple">▤</span>
                    <span class="workspace-card-title">文档管理</span>
                    <span class="workspace-card-description">
                      上传 PDF、DOCX、Markdown 和 TXT 文档。
                    </span>
                    <span class="workspace-card-action">进入文档管理 →</span>
                  </button>

                  <button
                    type="button"
                    class="workspace-card"
                    @click="switchTab('search')"
                  >
                    <span class="workspace-card-icon blue">⌕</span>
                    <span class="workspace-card-title">混合检索</span>
                    <span class="workspace-card-description">
                      使用 BM25 与向量检索查找相关知识。
                    </span>
                    <span class="workspace-card-action">进入混合检索 →</span>
                  </button>

                  <button
                    type="button"
                    class="workspace-card"
                    @click="switchTab('rag')"
                  >
                    <span class="workspace-card-icon green">✧</span>
                    <span class="workspace-card-title">RAG 智能问答</span>
                    <span class="workspace-card-description">
                      基于知识库内容回答问题，展示引用来源。
                    </span>
                    <span class="workspace-card-action">进入 RAG 问答 →</span>
                  </button>

                  <button
                    type="button"
                    class="workspace-card"
                    @click="switchTab('agent')"
                  >
                    <span class="workspace-card-icon orange">⌘</span>
                    <span class="workspace-card-title">Agent 助手</span>
                    <span class="workspace-card-description">
                      自主规划任务，按需调用知识库工具。
                    </span>
                    <span class="workspace-card-action">进入 Agent 助手 →</span>
                  </button>
                </div>
              </section>
            </div>

            <!-- 文档管理 -->
            <div v-show="activeTab === 'documents'" class="module-content">
              <DocumentUploadPanel :knowledge-base-id="store.current.id" />
            </div>

            <!-- 混合检索 -->
            <div v-show="activeTab === 'search'" class="module-content">
              <DocumentSearchPanel :knowledge-base-id="store.current.id" />
            </div>

            <!-- RAG -->
            <div v-show="activeTab === 'rag'" class="module-content">
              <RAGChatPanel :knowledge-base-id="store.current.id" />
            </div>

            <!-- Agent -->
            <div v-show="activeTab === 'agent'" class="module-content">
              <AgentChatPanel :knowledge-base-id="store.current.id" />
            </div>
          </section>
        </section>
      </template>
    </main>

    <footer class="knowledge-footer">
      <span>KnowledgeFlow</span>
      <span>本地优先的智能知识库系统</span>
    </footer>
  </div>
</template>

<style scoped>
.knowledge-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f7f8fc;
}

.knowledge-topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 68px;
  padding: 0 max(6%, calc((100% - 1200px) / 2));
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgb(255 255 255 / 96%);
  border-bottom: 1px solid #e9eaf1;
  backdrop-filter: blur(12px);
}

.knowledge-brand {
  display: inline-flex;
  align-items: center;
  gap: 11px;
  color: #25243a;
  font-size: 18px;
  font-weight: 700;
  text-decoration: none;
}

.brand-logo {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  object-fit: contain;
  border-radius: 8px;
}

.back-link {
  color: #77788d;
  font-size: 13px;
  text-decoration: none;
}

.back-link:hover,
.breadcrumb a:hover {
  color: #6558d3;
}

.back-link span {
  margin-right: 6px;
}

.knowledge-main {
  width: min(1200px, 88%);
  flex: 1;
  margin: 0 auto;
  padding: 28px 0 55px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 22px;
  color: #9999a9;
  font-size: 12px;
}

.breadcrumb a {
  color: #77788d;
  text-decoration: none;
}

.breadcrumb-current {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-header {
  min-height: 116px;
  padding: 22px 26px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  border: 1px solid #e9eaf1;
  border-radius: 14px;
  background: #fff;
}

.knowledge-heading-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 17px;
}

.knowledge-heading-text {
  min-width: 0;
}

.knowledge-large-icon {
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 14px;
  color: #6b5dd1;
  background: #f0edff;
  font-size: 26px;
}

.knowledge-eyebrow,
.workspace-eyebrow {
  margin-bottom: 6px;
  color: #8175d7;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.7px;
}

.knowledge-header h1 {
  margin: 0;
  overflow-wrap: anywhere;
  color: #25243a;
  font-size: 22px;
}

.knowledge-header p {
  margin: 7px 0 0;
  color: #85869a;
  font-size: 12px;
  line-height: 1.6;
}

.knowledge-status,
.overview-status {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 11px;
  border-radius: 20px;
  color: #259b72;
  background: #eaf8f2;
  font-size: 11px;
}

.knowledge-status span,
.overview-status span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #32b987;
}

.workspace {
  margin-top: 24px;
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  align-items: start;
  gap: 20px;
}

.workspace-nav {
  position: sticky;
  top: 88px;
  padding: 9px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  border: 1px solid #e9eaf1;
  border-radius: 13px;
  background: #fff;
}

.workspace-nav-item {
  min-height: 43px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  border-radius: 8px;
  color: #696b80;
  background: transparent;
  font-size: 13px;
  text-align: left;
  transition: background 0.18s, color 0.18s;
}

.workspace-nav-item:hover {
  color: #6558d3;
  background: #f7f6ff;
}

.workspace-nav-item.active {
  color: #5c4fc9;
  background: #f0edff;
  font-weight: 600;
}

.nav-icon {
  width: 20px;
  flex: 0 0 auto;
  font-size: 17px;
  text-align: center;
}

.workspace-content {
  min-width: 0;
  padding: 23px;
  border: 1px solid #e9eaf1;
  border-radius: 13px;
  background: #fff;
}

.workspace-heading {
  padding-bottom: 19px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  border-bottom: 1px solid #eff0f5;
}

.workspace-heading h2 {
  margin: 0;
  color: #25243a;
  font-size: 19px;
}

.workspace-heading p {
  margin: 7px 0 0;
  color: #85869a;
  font-size: 12px;
  line-height: 1.6;
}

.workspace-id {
  flex: 0 0 auto;
  padding: 6px 9px;
  border-radius: 7px;
  color: #77788d;
  background: #f5f5f9;
  font-size: 11px;
}

.overview-content {
  padding-top: 20px;
}

.overview-info {
  padding: 19px;
  border: 1px solid #ececf3;
  border-radius: 11px;
  background: #fcfcfe;
}

.overview-info-heading,
.overview-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.overview-info h3,
.overview-section-heading h3 {
  margin: 0;
  color: #343349;
  font-size: 14px;
}

.overview-info-heading p {
  margin: 6px 0 0;
  color: #9293a5;
  font-size: 11px;
}

.overview-meta {
  margin-top: 20px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 15px;
}

.overview-meta > div {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.overview-meta span {
  color: #9293a5;
  font-size: 11px;
}

.overview-meta strong {
  overflow-wrap: anywhere;
  color: #343349;
  font-size: 13px;
}

.overview-functions {
  margin-top: 25px;
}

.overview-section-heading {
  margin-bottom: 13px;
}

.overview-section-heading > span {
  color: #9999a9;
  font-size: 11px;
}

.workspace-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 13px;
}

.workspace-card {
  min-width: 0;
  min-height: 158px;
  padding: 17px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  border: 1px solid #e9eaf1;
  border-radius: 11px;
  background: #fff;
  text-align: left;
  transition: transform 0.18s, border-color 0.18s, box-shadow 0.18s;
}

.workspace-card:hover {
  transform: translateY(-2px);
  border-color: #d7d1f7;
  box-shadow: 0 7px 20px rgb(37 36 58 / 5%);
}

.workspace-card-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  font-size: 19px;
}

.workspace-card-icon.purple {
  color: #7061d8;
  background: #f0edff;
}

.workspace-card-icon.blue {
  color: #4389d2;
  background: #eaf3ff;
}

.workspace-card-icon.green {
  color: #2baf83;
  background: #e8f8f1;
}

.workspace-card-icon.orange {
  color: #d78a43;
  background: #fff3e6;
}

.workspace-card-title {
  margin-top: 12px;
  color: #343349;
  font-size: 13px;
  font-weight: 650;
}

.workspace-card-description {
  margin-top: 6px;
  color: #85869a;
  font-size: 11px;
  line-height: 1.7;
}

.workspace-card-action {
  margin-top: auto;
  padding-top: 12px;
  color: #6558d3;
  font-size: 11px;
  font-weight: 600;
}

.module-content {
  min-width: 0;
  padding-top: 20px;
}

/* 业务组件在工作区内占满可用宽度 */
.module-content :deep(.upload-panel),
.module-content :deep(.search-panel),
.module-content :deep(.rag-panel),
.module-content :deep(.agent-panel) {
  width: 100%;
  max-width: 100%;
}

.detail-state {
  min-height: 330px;
  padding: 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px solid #e9eaf1;
  border-radius: 14px;
  background: #fff;
  text-align: center;
}

.detail-state p {
  margin: 12px 0 20px;
  color: #85869a;
  font-size: 13px;
}

.detail-state h2 {
  margin: 17px 0 0;
  color: #343349;
  font-size: 18px;
}

.loading-spinner {
  width: 29px;
  height: 29px;
  border: 3px solid #e9e6fb;
  border-top-color: #6558d3;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.detail-error-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #d94c61;
  background: #fff0f1;
  font-weight: 700;
}

.detail-primary-button {
  padding: 10px 16px;
  border-radius: 8px;
  color: #fff;
  background: #6558d3;
  font-size: 12px;
  text-decoration: none;
}

.knowledge-footer {
  min-height: 60px;
  padding: 15px 6%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid #e9eaf1;
  color: #9999a9;
  background: #fff;
  font-size: 11px;
}

@media (max-width: 850px) {
  .knowledge-main {
    width: 92%;
  }

  .workspace {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .workspace-nav {
    position: static;
    flex-direction: row;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .workspace-nav-item {
    flex: 0 0 auto;
    justify-content: center;
  }
}

@media (max-width: 600px) {
  .knowledge-topbar {
    height: 60px;
    padding: 0 5%;
  }

  .knowledge-brand {
    font-size: 16px;
  }

  .knowledge-main {
    width: 92%;
    padding-top: 20px;
  }

  .breadcrumb {
    gap: 7px;
    margin-bottom: 16px;
  }

  .knowledge-header {
    align-items: flex-start;
    flex-direction: column;
    padding: 19px;
  }

  .knowledge-heading-main {
    align-items: flex-start;
    gap: 12px;
  }

  .knowledge-large-icon {
    width: 43px;
    height: 43px;
    font-size: 22px;
  }

  .knowledge-header h1 {
    font-size: 19px;
  }

  .workspace-content {
    padding: 16px;
  }

  .workspace-heading h2 {
    font-size: 17px;
  }

  .workspace-nav {
    padding: 6px;
    gap: 3px;
  }

  .workspace-nav-item {
    min-height: 39px;
    padding: 0 10px;
    font-size: 12px;
  }

  .workspace-cards {
    grid-template-columns: 1fr;
  }

  .workspace-card {
    min-height: 145px;
  }

  .overview-meta {
    grid-template-columns: 1fr;
  }

  .overview-info-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .knowledge-footer {
    gap: 10px;
    flex-wrap: wrap;
  }
}
</style>
