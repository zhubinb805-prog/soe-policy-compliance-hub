<template>
  <div class="conversation-manager">
    <el-card shadow="never" class="search-card">
      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="搜索会话标题或消息内容..."
          clearable
          @input="handleSearch"
        >
          <template #append>
            <el-button @click="handleSearch"><el-icon name="Search" /></el-button>
          </template>
        </el-input>
        <el-input
          v-model="filterUserId"
          placeholder="筛选用户ID..."
          clearable
          @input="loadConversations"
        />
      </div>
    </el-card>

    <el-card shadow="never" class="list-card">
      <template #header>
        <div class="header-row">
          <span class="list-title">会话列表</span>
          <el-tag type="info" size="small">共 {{ totalCount }} 条</el-tag>
        </div>
      </template>

      <div v-if="conversations.length === 0" class="empty-state">
        <el-icon name="MessageSquare" class="empty-icon" />
        <p>暂无会话记录</p>
      </div>

      <el-table v-else :data="conversations" border stripe class="conversation-table">
        <el-table-column prop="session_id" label="会话ID" width="200" />
        <el-table-column prop="user_id" label="用户ID" width="150" />
        <el-table-column prop="title" label="标题">
          <template #default="scope">
            <div class="title-cell">
              <el-input
                v-if="editingId === scope.row.session_id"
                v-model="editTitle"
                class="title-input"
                @blur="saveTitle(scope.row.session_id)"
                @keyup.enter="saveTitle(scope.row.session_id)"
              />
              <span v-else class="title-text">{{ scope.row.title || '未命名会话' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="200">
          <template #default="scope">{{ formatTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="200">
          <template #default="scope">{{ formatTime(scope.row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250">
          <template #default="scope">
            <el-button
              size="small"
              @click="viewConversation(scope.row.session_id)"
              type="primary"
            >
              <el-icon name="Eye" /> 查看
            </el-button>
            <el-button
              size="small"
              @click="startEditTitle(scope.row)"
              type="warning"
            >
              <el-icon name="Edit" /> 编辑标题
            </el-button>
            <el-button
              size="small"
              @click="confirmDeleteConversation(scope.row.session_id)"
              type="danger"
            >
              <el-icon name="Delete" /> 删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="totalCount > pageSize"
        :current-page="currentPage"
        :page-size="pageSize"
        :total="totalCount"
        layout="prev, pager, next, jumper"
        @current-change="handlePageChange"
        class="pagination"
      />
    </el-card>

    <el-dialog
      v-if="showDetail"
      :title="selectedConversation?.title || '会话详情'"
      v-model:visible="showDetail"
      width="800px"
    >
      <div v-if="selectedConversation" class="conversation-detail">
        <div class="detail-header">
          <div class="detail-info">
            <span class="detail-label">会话ID:</span>
            <span>{{ selectedConversation.session_id }}</span>
          </div>
          <div class="detail-info">
            <span class="detail-label">用户ID:</span>
            <span>{{ selectedConversation.user_id }}</span>
          </div>
          <div class="detail-info">
            <span class="detail-label">创建时间:</span>
            <span>{{ formatTime(selectedConversation.created_at) }}</span>
          </div>
        </div>

        <el-divider />

        <div class="messages-container">
          <div class="messages-header">
            <span class="messages-title">消息列表 ({{ selectedConversation.messages.length }})</span>
          </div>

          <div v-if="selectedConversation.messages.length === 0" class="empty-messages">
            <p>该会话暂无消息</p>
          </div>

          <div v-else class="messages-list">
            <div
              v-for="message in selectedConversation.messages"
              :key="message.id"
              :class="['message-item', message.role]"
            >
              <div class="message-header">
                <span class="message-role">{{ message.role === 'user' ? '用户' : '助手' }}</span>
                <span class="message-time">{{ formatTime(message.timestamp) }}</span>
                <el-button
                  size="mini"
                  @click="confirmDeleteMessage(selectedConversation.session_id, message.id)"
                  type="danger"
                  icon="Delete"
                />
              </div>
              <div class="message-content">{{ message.content }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getConversationList,
  getConversation,
  searchConversations,
  updateConversationTitle,
  deleteConversation,
  deleteMessage
} from '../api'

const conversations = ref([])
const searchQuery = ref('')
const filterUserId = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const loading = ref(false)

const showDetail = ref(false)
const selectedConversation = ref(null)
const editingId = ref(null)
const editTitle = ref('')

const handleSearch = () => {
  currentPage.value = 1
  loadConversations()
}

const loadConversations = async () => {
  loading.value = true
  try {
    if (searchQuery.value.trim()) {
      const response = await searchConversations({
        query: searchQuery.value,
        user_id: filterUserId.value || undefined,
        limit: pageSize.value
      })
      conversations.value = response
      totalCount.value = response.length
    } else {
      const response = await getConversationList({
        user_id: filterUserId.value || undefined,
        limit: pageSize.value,
        offset: (currentPage.value - 1) * pageSize.value
      })
      conversations.value = response
      totalCount.value = response.length
    }
  } catch (error) {
    ElMessage.error('加载会话列表失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  loadConversations()
}

const viewConversation = async (sessionId) => {
  try {
    selectedConversation.value = await getConversation(sessionId)
    showDetail.value = true
  } catch (error) {
    ElMessage.error('获取会话详情失败: ' + (error.response?.data?.detail || error.message))
  }
}

const startEditTitle = (row) => {
  editingId.value = row.session_id
  editTitle.value = row.title || ''
}

const saveTitle = async (sessionId) => {
  try {
    await updateConversationTitle(sessionId, editTitle.value)
    const conversation = conversations.value.find(c => c.session_id === sessionId)
    if (conversation) {
      conversation.title = editTitle.value
    }
    ElMessage.success('标题更新成功')
  } catch (error) {
    ElMessage.error('更新标题失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    editingId.value = null
    editTitle.value = ''
  }
}

const confirmDeleteConversation = (sessionId) => {
  ElMessageBox.confirm(
    '确定要删除这个会话吗？删除后将无法恢复。',
    '提示',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await deleteConversation(sessionId)
      conversations.value = conversations.value.filter(c => c.session_id !== sessionId)
      totalCount.value--
      ElMessage.success('删除成功')
    } catch (error) {
      ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message))
    }
  }).catch(() => {})
}

const confirmDeleteMessage = (sessionId, messageId) => {
  ElMessageBox.confirm(
    '确定要删除这条消息吗？',
    '提示',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await deleteMessage(sessionId, messageId)
      if (selectedConversation.value) {
        selectedConversation.value.messages = selectedConversation.value.messages.filter(
          m => m.id !== messageId
        )
      }
      ElMessage.success('删除成功')
    } catch (error) {
      ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message))
    }
  }).catch(() => {})
}

const formatTime = (timestamp) => {
  if (!timestamp) return '-'
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

onMounted(() => {
  loadConversations()
})
</script>

<style scoped>
.conversation-manager {
  width: 100%;
}

.search-card {
  margin-bottom: 20px;
}

.search-bar {
  display: flex;
  gap: 12px;
}

.search-bar .el-input {
  flex: 1;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.list-title {
  font-weight: 600;
  font-size: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--el-text-color-secondary);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.conversation-table {
  margin-bottom: 16px;
}

.title-cell {
  width: 100%;
}

.title-input {
  width: 100%;
}

.title-text {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

.pagination {
  text-align: right;
}

.conversation-detail {
  max-height: 600px;
  overflow-y: auto;
}

.detail-header {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}

.detail-info {
  display: flex;
  gap: 8px;
}

.detail-label {
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.messages-container {
  margin-top: 16px;
}

.messages-header {
  margin-bottom: 12px;
}

.messages-title {
  font-weight: 600;
}

.empty-messages {
  text-align: center;
  padding: 20px;
  color: var(--el-text-color-secondary);
}

.messages-list {
  max-height: 400px;
  overflow-y: auto;
}

.message-item {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 8px;
}

.message-item.user {
  background: var(--el-color-primary-light-9);
  border-left: 4px solid var(--el-color-primary);
}

.message-item.assistant {
  background: var(--el-fill-color-light);
  border-left: 4px solid var(--el-color-success);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.message-role {
  font-weight: 600;
}

.message-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.message-content {
  font-size: 14px;
  line-height: 1.6;
}
</style>