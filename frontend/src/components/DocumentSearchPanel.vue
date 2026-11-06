<script setup lang="ts">
import { ref } from 'vue'
import { searchApi } from '../api/search'
import { getApiErrorMessage } from '../api/http'
import type { SearchResultItem } from '../types/api'

const props = defineProps<{
  knowledgeBaseId: number
}>()

const query = ref('')
const topK = ref(5)
const loading = ref(false)
const errorMessage = ref('')
const results = ref<SearchResultItem[]>([])
const searched = ref(false)

function formatScore(value: number | null): string {
  return value === null ? '-' : value.toFixed(5)
}

async function search() {
  const keyword = query.value.trim()

  if (!keyword || loading.value) {
    return
  }

  loading.value = true
  errorMessage.value = ''
  searched.value = false
  results.value = []

  try {
    const response = await searchApi.search(props.knowledgeBaseId, {
      query: keyword,
      top_k: topK.value,
    })

    results.value = response.data.results
    searched.value = true
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '检索失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="search-panel">
    <div class="search-heading">
      <div>
        <div class="search-title-row">
          <span class="search-icon">⌕</span>
          <h2>混合检索</h2>
        </div>
        <p>结合向量语义检索与 BM25 关键词检索，通过 RRF 融合相关结果。</p>
      </div>
      <span class="search-engine">BM25 + Vector + RRF</span>
    </div>

    <form class="search-form" @submit.prevent="search">
      <div class="search-input-wrap">
        <span class="input-search-icon">⌕</span>
        <input
          v-model="query"
          type="text"
          maxlength="10000"
          placeholder="输入关键词或自然语言问题，搜索知识库内容…"
          :disabled="loading"
        />
        <button
          class="search-button"
          type="submit"
          :disabled="loading || !query.trim()"
        >
          {{ loading ? '检索中…' : '搜索' }}
        </button>
      </div>

      <div class="search-options">
        <label for="search-top-k">返回结果数量</label>
        <select id="search-top-k" v-model.number="topK" :disabled="loading">
          <option :value="3">3 条</option>
          <option :value="5">5 条</option>
          <option :value="10">10 条</option>
          <option :value="20">20 条</option>
          <option :value="50">50 条</option>
          <option :value="100">100 条</option>
        </select>
        <span>按照 RRF 综合相关性排序</span>
      </div>
    </form>

    <div v-if="loading" class="search-state">
      <div class="search-spinner"></div>
      <p>正在执行向量检索与关键词检索…</p>
    </div>

    <div v-else-if="errorMessage" class="search-error">
      <span>!</span>
      {{ errorMessage }}
    </div>

    <div v-else-if="searched && results.length === 0" class="search-empty">
      <span class="empty-search-icon">⌕</span>
      <strong>没有找到相关内容</strong>
      <p>尝试更换关键词，或使用更具体的描述。</p>
    </div>

    <div v-else-if="searched" class="search-results">
      <div class="results-heading">
        <strong>检索结果</strong>
        <span>共找到 {{ results.length }} 条相关分块</span>
      </div>

      <article
        v-for="(item, index) in results"
        :key="item.chunk_id"
        class="result-card"
      >
        <div class="result-topline">
          <div class="result-document">
            <span class="result-number">{{ index + 1 }}</span>
            <div class="result-document-info">
              <strong>{{ item.document_name }}</strong>
              <span>
                文档 ID：{{ item.document_id }}
                <span class="metadata-divider">·</span>
                分块：{{ item.chunk_index }}
                <span class="metadata-divider">·</span>
                {{ item.token_count }} tokens
              </span>
            </div>
          </div>
          <span class="rrf-score">RRF {{ formatScore(item.rrf_score) }}</span>
        </div>

        <p class="result-content">{{ item.content }}</p>

        <div class="result-scores">
          <span>向量距离：{{ formatScore(item.vector_distance) }}</span>
          <span>BM25 分数：{{ formatScore(item.bm25_score) }}</span>
          <span>分块 ID：{{ item.chunk_id }}</span>
        </div>
      </article>
    </div>

    <div v-else class="search-placeholder">
      <span>⌕</span>
      <p>输入关键词，开始探索知识库中的相关内容。</p>
    </div>
  </section>
</template>

<style scoped>
.search-panel {
  grid-column: 1 / -1;
  min-width: 0;
  padding: 23px;
  border: 1px solid #e9eaf1;
  border-radius: 12px;
  background: #fff;
}

.search-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 15px;
}

.search-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: #4389d2;
  background: #eaf3ff;
  font-size: 23px;
}

.search-title-row h2 {
  margin: 0;
  color: #343349;
  font-size: 17px;
}

.search-heading p {
  margin: 9px 0 0;
  color: #85869a;
  font-size: 12px;
  line-height: 1.7;
}

.search-engine {
  flex: 0 0 auto;
  padding: 7px 10px;
  border-radius: 6px;
  color: #4389d2;
  background: #eaf3ff;
  font-size: 10px;
}

.search-form {
  margin-top: 20px;
}

.search-input-wrap {
  min-height: 46px;
  padding: 5px 5px 5px 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #e3e2ed;
  border-radius: 9px;
  background: #fff;
}

.search-input-wrap:focus-within {
  border-color: #8b7de8;
  box-shadow: 0 0 0 3px rgb(101 88 211 / 8%);
}

.input-search-icon {
  color: #9999aa;
  font-size: 21px;
}

.search-input-wrap input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  color: #343349;
  background: transparent;
  font-size: 12px;
}

.search-input-wrap input::placeholder {
  color: #aaa9b8;
}

.search-button {
  min-width: 75px;
  height: 35px;
  border: 0;
  border-radius: 7px;
  color: #fff;
  background: #6558d3;
  font-size: 12px;
  font-weight: 600;
}

.search-button:hover:not(:disabled) {
  background: #5548c2;
}

.search-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.search-options {
  margin-top: 11px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #85869a;
  font-size: 11px;
}

.search-options select {
  padding: 5px 8px;
  border: 1px solid #e9eaf1;
  border-radius: 6px;
  outline: none;
  color: #55546b;
  background: #fff;
  font-size: 11px;
}

.search-options span {
  margin-left: auto;
}

.search-state,
.search-empty,
.search-placeholder {
  min-height: 135px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9293a5;
  text-align: center;
}

.search-state p,
.search-empty p,
.search-placeholder p {
  margin: 10px 0 0;
  font-size: 12px;
}

.search-spinner {
  width: 25px;
  height: 25px;
  border: 3px solid #e9e6fb;
  border-top-color: #6558d3;
  border-radius: 50%;
  animation: search-spin 0.8s linear infinite;
}

@keyframes search-spin {
  to {
    transform: rotate(360deg);
  }
}

.search-error {
  margin-top: 16px;
  padding: 12px;
  border-radius: 8px;
  color: #c34e60;
  background: #fff1f2;
  font-size: 12px;
  line-height: 1.6;
}

.search-error span {
  margin-right: 6px;
  font-weight: 700;
}

.empty-search-icon,
.search-placeholder > span {
  color: #b5b1d5;
  font-size: 30px;
}

.search-empty strong {
  margin-top: 8px;
  color: #55546b;
  font-size: 13px;
}

.search-results {
  margin-top: 22px;
}

.results-heading {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.results-heading strong {
  color: #343349;
  font-size: 13px;
}

.results-heading span {
  color: #9293a5;
  font-size: 11px;
}

.result-card {
  margin-top: 11px;
  padding: 15px;
  border: 1px solid #ececf2;
  border-radius: 9px;
  background: #fdfdff;
}

.result-topline {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.result-document {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.result-number {
  width: 27px;
  height: 27px;
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  border-radius: 7px;
  color: #6558d3;
  background: #f0edff;
  font-size: 11px;
  font-weight: 700;
}

.result-document-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.result-document-info strong {
  overflow-wrap: anywhere;
  color: #44445a;
  font-size: 12px;
}

.result-document-info > span {
  color: #9293a5;
  font-size: 10px;
}

.metadata-divider {
  margin: 0 4px;
}

.rrf-score {
  flex: 0 0 auto;
  padding: 5px 7px;
  border-radius: 5px;
  color: #6558d3;
  background: #f0edff;
  font-size: 10px;
  font-weight: 600;
}

.result-content {
  margin: 13px 0;
  color: #55546b;
  font-size: 12px;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.result-scores {
  padding-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  border-top: 1px solid #eeeef3;
  color: #9293a5;
  font-size: 10px;
}

@media (max-width: 600px) {
  .search-panel {
    padding: 16px;
  }

  .search-heading {
    flex-direction: column;
  }

  .search-input-wrap {
    gap: 7px;
    padding-left: 9px;
  }

  .search-button {
    min-width: 58px;
  }

  .search-options {
    flex-wrap: wrap;
  }

  .search-options span {
    margin-left: 0;
  }

  .result-topline {
    flex-direction: column;
  }
}
</style>
