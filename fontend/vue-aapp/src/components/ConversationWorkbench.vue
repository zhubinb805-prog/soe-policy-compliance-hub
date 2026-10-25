<template>
  <div class="conversation-workbench">
    <div class="workbench-header">
      <div class="header-left">
        <el-button
          type="primary"
          icon="Plus"
          @click="createNewConversation"
        >
          新建对话
        </el-button>
        <el-select
          v-model="currentSessionId"
          placeholder="选择会话"
          class="session-select"
          @change="loadConversation"
        >
          <el-option
            v-for="conv in conversationList"
            :key="conv.session_id"
            :label="conv.title || conv.session_id"
            :value="conv.session_id"
          />
        </el-select>
      </div>
      <div class="memory-toggle">
        <el-switch
          v-model="useMemory"
          :active-text="'启用记忆检索'"
          :inactive-text="'禁用记忆检索'"
        />
        <el-tooltip content="启用后，AI会参考历史对话记忆提供个性化回答" placement="top">
          <el-icon name="QuestionFilled" class="help-icon" />
        </el-tooltip>
      </div>
    </div>

    <div class="conversation-area">
      <div class="message-list" ref="messageListRef">
        <div
          v-for="message in messages"
          :key="message.id"
          :class="['message-item', message.role]"
        >
          <div class="message-avatar">
            <el-icon v-if="message.role === 'user'" name="User" />
            <el-icon v-else name="Bot" />
          </div>
          <div class="message-content-wrapper">
            <div class="message-header">
              <span class="message-role-label">{{ message.role === 'user' ? '用户' : '助手' }}</span>
              <span class="message-time">{{ formatTime(message.timestamp) }}</span>
            </div>
            <div
              v-if="message.role === 'assistant'"
              class="message-text markdown-body"
              v-html="renderMarkdown(message.content)"
            />
            <div v-else class="message-text">{{ message.content }}</div>
          </div>
        </div>

        <div v-if="loading" class="loading-indicator">
          <el-spinner size="medium" />
          <span>AI思考中...</span>
        </div>
      </div>
    </div>

    <div class="example-questions">
      <span class="example-label">合规问答示例</span>
      <el-button v-for="item in exampleQuestions" :key="item" text type="primary" @click="question = item">
        {{ item }}
      </el-button>
    </div>

    <el-card shadow="never" class="input-card">
      <div class="qa-input-row">
        <el-input
          v-model="question"
          placeholder="例如：采购金额超过 100 万元需要哪些审批？"
          size="large"
          clearable
          @keyup.enter="handleAsk"
          :disabled="loading"
        />
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          :disabled="!question.trim()"
          @click="handleAsk"
        >
          发送
        </el-button>
      </div>
    </el-card>

    <el-dialog
      v-if="showResult"
      :title="qaResult?.question || '回答结果'"
      v-model:visible="showResult"
      width="800px"
    >
      <div class="answer-text markdown-body" v-html="renderMarkdown(qaResult?.answer || '')" />
      <el-tag v-if="qaResult?.confidence != null" type="info" size="small" class="meta-tag">
        置信度: {{ (qaResult.confidence * 100).toFixed(1) }}%
      </el-tag>
      <el-tag v-if="qaResult?.intent" type="info" size="small" class="meta-tag">
        意图: {{ qaResult.intent }}
      </el-tag>

      <el-divider v-if="qaResult?.sources && qaResult.sources.length > 0" />
      <div v-if="qaResult?.sources && qaResult.sources.length > 0">
        <h5>参考来源</h5>
        <el-timeline>
          <el-timeline-item
            v-for="(source, i) in qaResult.sources"
            :key="i"
            :timestamp="source.page ? `${source.source} · 第 ${source.page} 页` : source.source"
            placement="top"
          >
            <el-card shadow="never">
              <p>{{ source.content }}</p>
              <span class="score">{{ source.type === 'graph' ? '知识图谱' : '语义检索' }} · 相关度 {{ source.score.toFixed(3) }}</span>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </div>

      <el-divider v-if="qaResult?.reasoning_steps && qaResult.reasoning_steps.length > 0" />
      <el-collapse v-if="qaResult?.reasoning_steps && qaResult.reasoning_steps.length > 0">
        <el-collapse-item title="处理过程">
          <ol>
            <li v-for="(step, i) in qaResult.reasoning_steps" :key="i">{{ step }}</li>
          </ol>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  askQuestion,
  retrieveMemory,
  createConversation,
  getConversation,
  addMessage,
  getConversationList
} from '../api'

const question = ref('')
const exampleQuestions = [
  '采购金额超过 100 万元需要哪些审批？',
  '采购申请部门和采购管理部各自承担什么责任？',
  '哪些行为会被认定为重大合规风险？'
]
const qaResult = ref(null)
const loading = ref(false)
const useMemory = ref(true)
const showResult = ref(false)

const messages = ref([])
const currentSessionId = ref('')
const conversationList = ref([])
const messageListRef = ref(null)

// Render the model's Markdown without trusting arbitrary HTML from the model.
// Escaping happens before the small Markdown subset is converted to HTML.
const escapeHtml = (value) => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const renderInlineMarkdown = (value) => value
  .replace(/`([^`]+)`/g, '<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  .replace(/__([^_]+)__/g, '<strong>$1</strong>')
  .replace(/\*([^*]+)\*/g, '<em>$1</em>')

const renderMarkdown = (value) => {
  if (!value) return ''

  // Some providers return escaped newline characters instead of real newlines.
  const source = String(value)
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\r\n?/g, '\n')
    // Make inline headings/lists readable even when the model omitted a newline.
    .replace(/[ \t]+(?=#{1,6}\s)/g, '\n')
    .replace(/[ \t]+(?=(?:[-*])\s+\*\*)/g, '\n')
    .replace(/[ \t]+(?=\d+\.\s+)/g, '\n')

  const lines = escapeHtml(source).split('\n')
  const html = []
  let listType = null

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`)
      listType = null
    }
  }

  lines.forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      closeList()
      return
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      return
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      const nextType = ordered ? 'ol' : 'ul'
      if (listType !== nextType) {
        closeList()
        listType = nextType
        html.push(`<${listType}>`)
      }
      html.push(`<li>${renderInlineMarkdown((unordered || ordered)[1])}</li>`)
      return
    }

    if (trimmed.startsWith('&gt;')) {
      closeList()
      html.push(`<blockquote>${renderInlineMarkdown(trimmed.slice(4).trim())}</blockquote>`)
      return
    }

    closeList()
    html.push(`<p>${renderInlineMarkdown(trimmed)}</p>`)
  })

  closeList()
  return html.join('')
}

const generateSessionId = () => {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

const createNewConversation = async () => {
  try {
    const sessionId = generateSessionId()
    await createConversation({
      session_id: sessionId,
      user_id: 'default_user',
      title: '新对话'
    })
    currentSessionId.value = sessionId
    messages.value = []
    conversationList.value.unshift({
      session_id: sessionId,
      title: '新对话',
      user_id: 'default_user',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
    ElMessage.success('新对话已创建')
  } catch (error) {
    ElMessage.error('创建对话失败: ' + (error.response?.data?.detail || error.message))
  }
}

const loadConversationList = async () => {
  try {
    conversationList.value = await getConversationList({ limit: 50 })
    if (conversationList.value.length > 0) {
      currentSessionId.value = conversationList.value[0].session_id
      await loadConversation()
    }
  } catch (error) {
    ElMessage.warning('加载会话列表失败: ' + error.message)
  }
}

const loadConversation = async () => {
  if (!currentSessionId.value) return
  try {
    const conversation = await getConversation(currentSessionId.value)
    messages.value = conversation.messages || []
    scrollToBottom()
  } catch (error) {
    ElMessage.error('加载会话失败: ' + (error.response?.data?.detail || error.message))
  }
}

const handleAsk = async () => {
  if (!question.value.trim() || loading.value) return
  loading.value = true

  const userMessage = {
    id: `msg_${Date.now()}`,
    session_id: currentSessionId.value,
    role: 'user',
    content: question.value,
    timestamp: new Date().toISOString()
  }

  if (!currentSessionId.value) {
    await createNewConversation()
  }

  messages.value.push(userMessage)
  await addMessage(currentSessionId.value, {
    role: 'user',
    content: question.value
  })

  scrollToBottom()

  try {
    if (useMemory.value) {
      try {
        await retrieveMemory({
          query: question.value,
          user_id: 'default_user',
          top_k: 3
        })
      } catch (memoryError) {
        ElMessage.warning('记忆检索失败，但仍将继续问答: ' + memoryError.message)
      }
    }

    const result = await askQuestion(question.value, {
      session_id: currentSessionId.value,
      user_id: 'default_user'
    })
    qaResult.value = result

    const assistantMessage = {
      id: `msg_${Date.now()}_assistant`,
      session_id: currentSessionId.value,
      role: 'assistant',
      content: result.answer,
      timestamp: new Date().toISOString()
    }
    messages.value.push(assistantMessage)
    await addMessage(currentSessionId.value, {
      role: 'assistant',
      content: result.answer
    })

    scrollToBottom()
    showResult.value = true
  } catch (err) {
    ElMessage.error('提问失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
    question.value = ''
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadConversationList()
})
</script>

<style scoped>
.conversation-workbench {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workbench-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  gap: 12px;
}

.session-select {
  width: 200px;
}

.memory-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: var(--el-fill-color-light, #f8f9fa);
  border-radius: 6px;
  border: 1px solid var(--el-border-color-light, #ebeef5);
}

.help-icon {
  font-size: 16px;
  color: var(--el-text-color-secondary, #909399);
  cursor: help;
  margin-left: 5px;
}

.conversation-area {
  background: var(--el-bg-color, #ffffff);
  border-radius: 8px;
  border: 1px solid var(--el-border-color, #e4e7ed);
  overflow: hidden;
}

.message-list {
  height: 400px;
  overflow-y: auto;
  padding: 16px;
}

.message-item {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.message-item.user {
  flex-direction: row-reverse;
}

.message-item.user .message-content-wrapper {
  align-items: flex-end;
}

.message-item.user .message-text {
  background: var(--el-color-primary, #409eff);
  color: #ffffff;
  border-radius: 12px 0 12px 12px;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--el-fill-color-light);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-content-wrapper {
  display: flex;
  flex-direction: column;
  max-width: 70%;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.message-role-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.message-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.message-text {
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 0 12px 12px 12px;
  font-size: 14px;
  line-height: 1.6;
}

.message-text.markdown-body {
  white-space: normal;
  overflow-wrap: anywhere;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 2px 0 8px;
  color: var(--el-text-color-primary);
  line-height: 1.45;
}

.markdown-body :deep(h3) {
  font-size: 15px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 4px 0 10px;
  padding-left: 22px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--el-color-primary);
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-secondary);
}

.markdown-body :deep(code) {
  padding: 2px 4px;
  border-radius: 3px;
  background: var(--el-fill-color-dark);
  font-family: Consolas, monospace;
}

.loading-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
  color: var(--el-text-color-secondary);
}

.input-card {
  margin-top: auto;
}

.qa-input-row {
  display: flex;
  gap: 12px;
}

.qa-input-row .el-input {
  flex: 1;
}

.answer-text {
  font-size: 15px;
  line-height: 1.8;
  margin-bottom: 12px;
}

.answer-text.markdown-body {
  white-space: normal;
  overflow-wrap: anywhere;
}

.meta-tag {
  margin-right: 8px;
}

.score {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}
</style>
