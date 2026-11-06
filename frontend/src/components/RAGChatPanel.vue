<script setup lang="ts">
import { ref } from 'vue'
import { ragApi } from '../api/rag'
import { getApiErrorMessage } from '../api/http'
import type { RAGResponse } from '../types/api'

const props = defineProps<{
  knowledgeBaseId: number
}>()

const query = ref('')
const topK = ref(5)
const loading = ref(false)
const errorMessage = ref('')
const response = ref<RAGResponse | null>(null)

async function ask() {
  const question = query.value.trim()

  if (!question || loading.value) {
    return
  }

  loading.value = true
  errorMessage.value = ''
  response.value = null

  try {
    const result = await ragApi.ask(props.knowledgeBaseId, {
      query: question,
      top_k: topK.value,
    })

    response.value = result.data
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '问答请求失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function formatScore(value: number): string {
  return value.toFixed(5)
}
</script>

<template>
  <section class="rag-panel">
    <div class="rag-heading">
      <div>
        <div class="rag-title-row">
          <span class="rag-icon">✧</span>
          <h2>RAG 智能问答</h2>
        </div>
        <p>基于知识库检索相关资料，由本地大语言模型生成回答并提供来源引用。</p>
      </div>
      <span class="rag-engine">Local RAG</span>
    </div>

    <form class="rag-form" @submit.prevent="ask">
      <textarea
        v-model="query"
        maxlength="10000"
        rows="3"
        placeholder="请输入问题，例如：KnowledgeFlow 使用什么向量模型？"
        :disabled="loading"
      />

      <div class="rag-controls">
        <div class="rag-options">
          <label for="rag-top-k">检索数量</label>
          <select id="rag-top-k" v-model.number="topK" :disabled="loading">
            <option :value="3">3 条</option>
            <option :value="5">5 条</option>
            <option :value="10">10 条</option>
            <option :value="20">20 条</option>
            <option :value="50">50 条</option>
            <option :value="100">100 条</option>
          </select>
        </div>

        <button
          class="rag-submit"
          type="submit"
          :disabled="loading || !query.trim()"
        >
          {{ loading ? '正在思考…' : '提问' }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="rag-loading">
      <div class="rag-spinner"></div>
      <strong>正在检索知识并生成回答</strong>
      <p>正在调用混合检索与本地 Ollama 模型，请稍候…</p>
    </div>

    <div v-else-if="errorMessage" class="rag-error">
      <span>!</span>
      {{ errorMessage }}
    </div>

    <div v-else-if="response" class="rag-response">
      <div class="answer-heading">
        <div>
          <span class="answer-label">AI ANSWER</span>
          <h3>回答结果</h3>
        </div>
        <span class="answer-model">KnowledgeFlow RAG</span>
      </div>

      <div class="answer-content">{{ response.answer }}</div>

      <div class="rag-stats">
        <div>
          <strong>{{ response.retrieved_count }}</strong>
          <span>检索分块</span>
        </div>
        <div>
          <strong>{{ response.context_token_count }}</strong>
          <span>上下文 Token</span>
        </div>
        <div>
          <strong>{{ response.sources.length }}</strong>
          <span>引用来源</span>
        </div>
      </div>

      <section class="source-section">
        <div class="source-heading">
          <h3>参考来源</h3>
          <span>{{ response.sources.length }} 个来源</span>
        </div>

        <div v-if="response.sources.length === 0" class="no-sources">
          本次回答没有可展示的引用来源。
        </div>

        <article
          v-for="source in response.sources"
          :key="source.source_id"
          class="source-card"
        >
          <div class="source-topline">
            <div class="source-name">
              <span class="source-number">[{{ source.source_id }}]</span>
              <strong>{{ source.document_name }}</strong>
            </div>
            <span class="source-score">
              RRF {{ formatScore(source.rrf_score) }}
            </span>
          </div>

          <div class="source-meta">
            文档 ID：{{ source.document_id }}
            <span>·</span>
            分块 ID：{{ source.chunk_id }}
            <span>·</span>
            分块索引：{{ source.chunk_index }}
          </div>

          <p class="source-content">{{ source.content }}</p>
        </article>
      </section>
    </div>

    <div v-else class="rag-placeholder">
      <span>✧</span>
      <strong>向知识库提问</strong>
      <p>输入问题，AI 将检索相关文档并生成带有来源依据的回答。</p>
    </div>
  </section>
</template>

<style scoped>
.rag-panel {
  grid-column: 1 / -1;
  min-width: 0;
  padding: 23px;
  border: 1px solid #e9eaf1;
  border-radius: 12px;
  background: #fff;
}

.rag-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 15px;
}

.rag-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rag-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #2baf83;
  background: #e8f8f1;
  font-size: 21px;
}

.rag-title-row h2 {
  margin: 0;
  color: #343349;
  font-size: 17px;
}

.rag-heading p {
  margin: 9px 0 0;
  color: #85869a;
  font-size: 12px;
  line-height: 1.7;
}

.rag-engine {
  flex: 0 0 auto;
  padding: 7px 10px;
  border-radius: 6px;
  color: #259b72;
  background: #e8f8f1;
  font-size: 10px;
}

.rag-form {
  margin-top: 20px;
}

.rag-form textarea {
  width: 100%;
  min-height: 85px;
  padding: 13px;
  resize: vertical;
  border: 1px solid #e3e2ed;
  border-radius: 9px;
  outline: none;
  color: #343349;
  background: #fff;
  font-size: 12px;
  line-height: 1.7;
}

.rag-form textarea:focus {
  border-color: #8b7de8;
  box-shadow: 0 0 0 3px rgb(101 88 211 / 8%);
}

.rag-form textarea::placeholder {
  color: #aaa9b8;
}

.rag-controls {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.rag-options {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #85869a;
  font-size: 11px;
}

.rag-options select {
  padding: 6px 9px;
  border: 1px solid #e9eaf1;
  border-radius: 6px;
  outline: none;
  color: #55546b;
  background: #fff;
  font-size: 11px;
}

.rag-submit {
  min-width: 85px;
  height: 36px;
  padding: 0 15px;
  border: 0;
  border-radius: 7px;
  color: #fff;
  background: #6558d3;
  font-size: 12px;
  font-weight: 600;
}

.rag-submit:hover:not(:disabled) {
  background: #5548c2;
}

.rag-submit:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.rag-loading,
.rag-placeholder {
  min-height: 150px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9293a5;
  text-align: center;
}

.rag-loading strong,
.rag-placeholder strong {
  margin-top: 12px;
  color: #55546b;
  font-size: 13px;
}

.rag-loading p,
.rag-placeholder p {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.7;
}

.rag-spinner {
  width: 27px;
  height: 27px;
  border: 3px solid #e9e6fb;
  border-top-color: #6558d3;
  border-radius: 50%;
  animation: rag-spin 0.8s linear infinite;
}

@keyframes rag-spin {
  to {
    transform: rotate(360deg);
  }
}

.rag-placeholder > span {
  color: #79c7a9;
  font-size: 31px;
}

.rag-error {
  margin-top: 16px;
  padding: 12px;
  border-radius: 8px;
  color: #c34e60;
  background: #fff1f2;
  font-size: 12px;
  line-height: 1.6;
}

.rag-error span {
  margin-right: 6px;
  font-weight: 700;
}

.rag-response {
  margin-top: 24px;
}

.answer-heading,
.source-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.answer-label {
  color: #259b72;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 1px;
}

.answer-heading h3,
.source-heading h3 {
  margin: 5px 0 0;
  color: #343349;
  font-size: 14px;
}

.answer-model {
  color: #9293a5;
  font-size: 10px;
}

.answer-content {
  margin-top: 13px;
  padding: 17px;
  border: 1px solid #e3f1ea;
  border-radius: 9px;
  color: #44445a;
  background: #f5fbf7;
  font-size: 13px;
  line-height: 2;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.rag-stats {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.rag-stats > div {
  min-height: 65px;
  padding: 11px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  border: 1px solid #ececf2;
  border-radius: 8px;
  background: #fdfdff;
}

.rag-stats strong {
  color: #5550b5;
  font-size: 16px;
}

.rag-stats span {
  color: #9293a5;
  font-size: 10px;
}

.source-section {
  margin-top: 23px;
}

.source-heading {
  margin-bottom: 12px;
}

.source-heading h3 {
  margin: 0;
}

.source-heading > span {
  color: #9293a5;
  font-size: 10px;
}

.source-card {
  margin-top: 10px;
  padding: 14px;
  border: 1px solid #ececf2;
  border-radius: 9px;
  background: #fdfdff;
}

.source-topline {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.source-name {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-name strong {
  overflow-wrap: anywhere;
  color: #44445a;
  font-size: 12px;
}

.source-number {
  flex: 0 0 auto;
  color: #259b72;
  font-size: 11px;
  font-weight: 700;
}

.source-score {
  flex: 0 0 auto;
  color: #6558d3;
  font-size: 10px;
}

.source-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  color: #9293a5;
  font-size: 10px;
}

.source-content {
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px solid #eeeef3;
  color: #666579;
  font-size: 11px;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.no-sources {
  padding: 15px;
  color: #9293a5;
  font-size: 11px;
  text-align: center;
}

@media (max-width: 600px) {
  .rag-panel {
    padding: 16px;
  }

  .rag-heading {
    flex-direction: column;
  }

  .rag-stats {
    gap: 6px;
  }

  .rag-stats > div {
    padding: 8px;
  }

  .source-topline {
    flex-direction: column;
  }
}
</style>
