<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { documentApi } from '../api/document'
import { getApiErrorMessage } from '../api/http'
import type { DocumentUploadResponse } from '../types/api'

const props = defineProps<{
  knowledgeBaseId: number
}>()

const MAX_FILE_SIZE = 20 * 1024 * 1024
const ACCEPTED_EXTENSIONS = ['pdf', 'docx', 'md', 'txt']

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const progress = ref(0)
const dragOver = ref(false)
const errorMessage = ref('')
const successResult = ref<DocumentUploadResponse | null>(null)

const inputElement = ref<HTMLInputElement | null>(null)

function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function validateFile(file: File): string | null {
  const extension = file.name.split('.').pop()?.toLowerCase()

  if (!extension || !ACCEPTED_EXTENSIONS.includes(extension)) {
    return '不支持该文件格式，请选择 PDF、DOCX、MD 或 TXT 文件'
  }

  if (file.size === 0) {
    return '不能上传空文件'
  }

  if (file.size > MAX_FILE_SIZE) {
    return '文件超过 20 MiB，请选择较小的文件'
  }

  return null
}

function chooseFile(file: File | undefined) {
  if (!file || uploading.value) {
    return
  }

  errorMessage.value = ''
  successResult.value = null
  progress.value = 0

  const validationError = validateFile(file)

  if (validationError) {
    selectedFile.value = null
    errorMessage.value = validationError
    return
  }

  selectedFile.value = file
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  chooseFile(input.files?.[0])
  input.value = ''
}

function handleDrop(event: DragEvent) {
  dragOver.value = false
  chooseFile(event.dataTransfer?.files[0])
}

function formatUploadError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 409) {
      const message =
        typeof detail?.message === 'string'
          ? detail.message
          : '该知识库中已存在相同内容的文档'

      const documentId =
        typeof detail?.document_id === 'number'
          ? detail.document_id
          : null

      return documentId === null
        ? message
        : `${message}（原文档 ID：${documentId}）`
    }

    if (status === 413) {
      return '文件超过服务器允许的大小限制（20 MiB）'
    }

    if (status === 400) {
      return getApiErrorMessage(error, '文件格式或内容校验失败')
    }

    if (status === 422) {
      return getApiErrorMessage(error, '文档内容为空或无法生成有效分块')
    }

    if (status === 404) {
      return '目标知识库不存在，请返回工作台重新选择'
    }
  }

  return getApiErrorMessage(error, '文档上传失败，请稍后重试')
}

async function uploadFile() {
  if (!selectedFile.value || uploading.value) {
    return
  }

  uploading.value = true
  errorMessage.value = ''
  successResult.value = null
  progress.value = 0

  try {
    const response = await documentApi.upload(
      props.knowledgeBaseId,
      selectedFile.value,
      (value) => {
        progress.value = value
      },
    )

    progress.value = 100
    successResult.value = response.data
    selectedFile.value = null
  } catch (error) {
    errorMessage.value = formatUploadError(error)
  } finally {
    uploading.value = false
  }
}

function clearSelection() {
  if (uploading.value) {
    return
  }

  selectedFile.value = null
  errorMessage.value = ''
  successResult.value = null
  progress.value = 0
}
</script>

<template>
  <section class="upload-panel">
    <div class="upload-heading">
      <div>
        <h2>文档导入</h2>
        <p>上传本地文档，自动完成解析、分块和向量索引。</p>
      </div>
      <span class="upload-count">20 MiB / 文件</span>
    </div>

    <div
      class="drop-zone"
      :class="{ 'drag-active': dragOver, 'upload-disabled': uploading }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="handleDrop"
      @click="!uploading && inputElement?.click()"
    >
      <input
        ref="inputElement"
        class="file-input"
        type="file"
        accept=".pdf,.docx,.md,.txt"
        :disabled="uploading"
        @change="handleFileChange"
      />

      <div class="upload-icon">↑</div>
      <h3>拖放文件到这里，或点击选择</h3>
      <p>支持 PDF、DOCX、MD、TXT 格式</p>
      <span class="upload-hint">单个文件最大 20 MiB</span>
    </div>

    <div v-if="selectedFile" class="selected-file">
      <div class="file-symbol">▤</div>
      <div class="file-information">
        <strong>{{ selectedFile.name }}</strong>
        <span>{{ formatFileSize(selectedFile.size) }}</span>
      </div>
      <button
        class="remove-file"
        type="button"
        :disabled="uploading"
        aria-label="取消选择"
        @click="clearSelection"
      >
        ×
      </button>
    </div>

    <div v-if="uploading" class="upload-progress">
      <div class="progress-heading">
        <span>
          {{ progress >= 100 ? '文件已上传，正在解析并建立索引…' : '正在上传文件…' }}
        </span>
        <span>{{ progress }}%</span>
      </div>
      <div class="progress-track">
        <div class="progress-value" :style="{ width: `${progress}%` }"></div>
      </div>
    </div>

    <p v-if="errorMessage" class="upload-error">
      <span>!</span>
      {{ errorMessage }}
    </p>

    <div v-if="successResult" class="upload-success">
      <div class="success-title">
        <span class="success-icon">✓</span>
        文档导入成功
      </div>
      <div class="success-details">
        <span>文档名称：{{ successResult.name }}</span>
        <span>文档 ID：{{ successResult.id }}</span>
        <span>文件大小：{{ formatFileSize(successResult.file_size) }}</span>
        <span>导入状态：{{ successResult.status }}</span>
      </div>
    </div>

    <div class="upload-actions">
      <button
        v-if="selectedFile"
        class="upload-button"
        type="button"
        :disabled="uploading"
        @click="uploadFile"
      >
        {{ uploading ? '正在导入…' : '开始上传并导入' }}
      </button>

      <button
        v-if="successResult"
        class="upload-secondary-button"
        type="button"
        @click="clearSelection"
      >
        继续上传
      </button>
    </div>
  </section>
</template>

<style scoped>
.upload-panel {
  grid-column: 1 / -1;
  padding: 23px;
  border: 1px solid #e9eaf1;
  border-radius: 12px;
  background: #fff;
}

.upload-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.upload-heading h2 {
  margin: 0;
  color: #343349;
  font-size: 17px;
}

.upload-heading p {
  margin: 8px 0 0;
  color: #85869a;
  font-size: 12px;
  line-height: 1.7;
}

.upload-count {
  flex: 0 0 auto;
  padding: 6px 9px;
  border-radius: 6px;
  color: #6b5dd1;
  background: #f0edff;
  font-size: 10px;
}

.drop-zone {
  min-height: 175px;
  margin-top: 20px;
  padding: 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px dashed #cbc7e9;
  border-radius: 10px;
  background: #fbfaff;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.drop-zone:hover,
.drop-zone.drag-active {
  border-color: #7869e8;
  background: #f5f3ff;
}

.drop-zone.upload-disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.file-input {
  display: none;
}

.upload-icon {
  width: 37px;
  height: 37px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #6b5dd1;
  background: #efedff;
  font-size: 23px;
}

.drop-zone h3 {
  margin: 12px 0 5px;
  color: #44445a;
  font-size: 13px;
}

.drop-zone p,
.upload-hint {
  margin: 4px 0;
  color: #9293a5;
  font-size: 11px;
}

.upload-hint {
  color: #aaa9b8;
}

.selected-file {
  margin-top: 15px;
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid #e9eaf1;
  border-radius: 9px;
}

.file-symbol {
  width: 35px;
  height: 35px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: #6b5dd1;
  background: #f0edff;
}

.file-information {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.file-information strong {
  overflow: hidden;
  color: #44445a;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-information span {
  color: #9293a5;
  font-size: 10px;
}

.remove-file {
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  color: #9999a9;
  background: #f5f5f9;
  font-size: 19px;
}

.upload-progress {
  margin-top: 17px;
}

.progress-heading {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  color: #77788d;
  font-size: 11px;
}

.progress-track {
  height: 6px;
  overflow: hidden;
  border-radius: 10px;
  background: #eeedf5;
}

.progress-value {
  height: 100%;
  border-radius: inherit;
  background: #6558d3;
  transition: width 0.2s;
}

.upload-error {
  margin: 14px 0 0;
  padding: 11px;
  border-radius: 8px;
  color: #c34e60;
  background: #fff1f2;
  font-size: 12px;
  line-height: 1.6;
}

.upload-error span {
  margin-right: 6px;
  font-weight: 700;
}

.upload-success {
  margin-top: 15px;
  padding: 14px;
  border-radius: 9px;
  color: #277f63;
  background: #effaf5;
}

.success-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
}

.success-icon {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: #35ad83;
}

.success-details {
  margin-top: 10px;
  display: grid;
  gap: 6px;
  color: #568875;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.upload-actions {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
  margin-top: 15px;
}

.upload-button,
.upload-secondary-button {
  min-height: 37px;
  padding: 0 15px;
  border: 0;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
}

.upload-button {
  color: #fff;
  background: #6558d3;
}

.upload-button:hover:not(:disabled) {
  background: #5548c2;
}

.upload-secondary-button {
  color: #6558d3;
  background: #f0edff;
}

.upload-button:disabled,
.upload-secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

@media (max-width: 600px) {
  .upload-panel {
    padding: 16px;
  }

  .upload-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
