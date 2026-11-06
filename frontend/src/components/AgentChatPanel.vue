<script setup lang="ts">
import { ref } from 'vue'
import { agentApi } from '../api/agent'
import { getApiErrorMessage } from '../api/http'
import type { AgentResponse } from '../types/api'

const props = defineProps<{
  knowledgeBaseId: number
}>()

const query = ref('')
const loading = ref(false)
const errorMessage = ref('')
const response = ref<AgentResponse | null>(null)

async function ask() {
  const question = query.value.trim()

  if (!question || loading.value) {
    return
  }

  loading.value = true
  errorMessage.value = ''
  response.value = null

  try {
    const result = await agentApi.ask(props.knowledgeBaseId, {
      query: question,
    })

    response.value = result.data
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, 'Agent 请求失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="agent-panel">
    <div class="agent-heading">
      <div>
        <div class="agent-title-row">
          <span class="agent-icon">⌘</span>
          <h2>Agent 智能助手</h2>
        </div>
        <p>Agent 可以自主判断问题、调用知识库检索工具，并组织最终回答。</p>
      </div>
      <span class="agent-engine">Local Agent</span>
    </div>

    <form class="agent-form" @submit.prevent="ask">
      <textarea
        v-model="query"
        maxlength="10000"
        rows="3"
        placeholder="请输入问题，例如：总结知识库中的技术架构，并说明关键组件。"
        :disabled="loading"
      />

      <div class="agent-controls">
        <span class="agent-hint">支持自主调用知识库检索工具</span>
        <button
          class="agent-submit"
          type="submit"
          :disabled="loading || !query.trim()"
        >
          {{ loading ? 'Agent 正在执行…' : '开始执行' }}
        </button>
      </div>
    </form>

    <div v-if="loading" class="agent-loading">
      <div class="agent-spinner"></div>
      <strong>Agent 正在分析问题</strong>
      <p>正在与本地模型交互，必要时会调用知识库工具，请稍候…</p>
    </div>

    <div v-else-if="errorMessage" class="agent-error">
      <span>!</span>
      {{ errorMessage }}
    </div>

    <div v-else-if="response" class="agent-response">
      <div class="agent-answer-heading">
        <div>
          <span class="agent-answer-label">AGENT ANSWER</span>
          <h3>执行结果</h3>
        </div>
        <span class="agent-answer-tag">KnowledgeFlow Agent</span>
      </div>

      <div class="agent-answer-content">{{ response.answer }}</div>

      <div class="agent-stats">
        <div>
          <strong>{{ response.tool_calls_count }}</strong>
          <span>工具调用次数</span>
        </div>
        <div>
          <strong>{{ response.iterations }}</strong>
          <span>执行轮数</span>
        </div>
        <div>
          <strong>{{ response.tool_calls_count > 0 ? '已调用' : '未调用' }}</strong>
          <span>知识库工具</span>
        </div>
      </div>

      <div class="agent-execution-info">
        <span class="execution-dot"></span>
        <span>
          {{
            response.tool_calls_count > 0
              ? 'Agent 已自主调用工具并完成回答。'
              : 'Agent 根据当前问题直接生成回答，未调用工具。'
          }}
        </span>
      </div>
    </div>

    <div v-else class="agent-placeholder">
      <span>⌘</span>
      <strong>让 Agent 帮你处理问题</strong>
      <p>与普通 RAG 问答不同，Agent 可以自主决定是否调用知识库工具。</p>
    </div>
  </section>
</template>

<style scoped>
.agent-panel {
  grid-column: 1 / -1;
  min-width: 0;
  padding: 23px;
  border: 1px solid #e9eaf1;
  border-radius: 16px;
  background: #fff;
}

.agent-heading,
.agent-title-row,
.agent-controls,
.agent-answer-heading,
.agent-execution-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.agent-title-row {
  justify-content: flex-start;
}

.agent-icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 10px;
  background: #fff2e7;
  color: #d97706;
  font-size: 21px;
}

.agent-heading h2 {
  margin: 0;
  color: #202436;
  font-size: 18px;
}

.agent-heading p,
.agent-loading p,
.agent-placeholder p {
  margin: 9px 0 0;
  color: #7c8193;
  font-size: 13px;
  line-height: 1.7;
}

.agent-engine,
.agent-answer-tag {
  flex-shrink: 0;
  padding: 6px 10px;
  border-radius: 20px;
  background: #fff5eb;
  color: #c46b19;
  font-size: 11px;
}

.agent-form {
  margin-top: 22px;
}

.agent-form textarea {
  box-sizing: border-box;
  width: 100%;
  min-height: 90px;
  resize: vertical;
  padding: 13px 15px;
  border: 1px solid #e4e6ed;
  border-radius: 10px;
  outline: none;
  color: #303548;
  font: inherit;
  font-size: 13px;
}

.agent-form textarea:focus {
  border-color: #e6a45e;
  box-shadow: 0 0 0 3px rgb(230 164 94 / 12%);
}

.agent-form textarea:disabled {
  background: #f8f9fb;
}

.agent-controls {
  margin-top: 12px;
}

.agent-hint {
  color: #858a9b;
  font-size: 12px;
}

.agent-submit {
  padding: 10px 22px;
  border: 0;
  border-radius: 9px;
  background: #d97706;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.agent-submit:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.agent-loading,
.agent-placeholder {
  display: flex;
  min-height: 145px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #555b70;
  text-align: center;
}

.agent-spinner {
  width: 25px;
  height: 25px;
  margin-bottom: 13px;
  border: 3px solid #f5dfc7;
  border-top-color: #d97706;
  border-radius: 50%;
  animation: agent-spin 0.8s linear infinite;
}

@keyframes agent-spin {
  to {
    transform: rotate(360deg);
  }
}

.agent-error {
  margin-top: 18px;
  padding: 13px;
  border-radius: 9px;
  background: #fff1f0;
  color: #c0392b;
  font-size: 13px;
}

.agent-error span {
  margin-right: 8px;
  font-weight: 700;
}

.agent-response {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #edf0f4;
}

.agent-answer-heading {
  justify-content: space-between;
}

.agent-answer-label {
  color: #d97706;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.2px;
}

.agent-answer-heading h3 {
  margin: 5px 0 0;
  color: #252a3b;
  font-size: 16px;
}

.agent-answer-content {
  margin-top: 17px;
  color: #41475a;
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 22px;
}

.agent-stats > div {
  display: flex;
  min-height: 75px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #f0e9e1;
  border-radius: 10px;
  background: #fffbf7;
}

.agent-stats strong {
  color: #c46b19;
  font-size: 21px;
}

.agent-stats span {
  color: #858a9b;
  font-size: 12px;
}

.agent-execution-info {
  justify-content: flex-start;
  margin-top: 17px;
  color: #747b8d;
  font-size: 12px;
}

.execution-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #16a36a;
}

.agent-placeholder {
  padding: 25px 0 10px;
}

.agent-placeholder > span {
  margin-bottom: 10px;
  color: #d97706;
  font-size: 27px;
}

.agent-placeholder strong,
.agent-loading strong {
  font-size: 14px;
}

@media (max-width: 600px) {
  .agent-panel {
    padding: 17px;
  }

  .agent-heading {
    align-items: flex-start;
  }

  .agent-engine {
    font-size: 10px;
  }

  .agent-stats {
    gap: 7px;
  }

  .agent-stats span {
    font-size: 10px;
  }

  .agent-controls {
    align-items: flex-start;
  }
}
</style>
