<template>
  <div class="knowledge-base">
    <el-card shadow="never" class="stats-card">
      <template #header>
        <span class="section-title">数据统计</span>
        <el-button type="primary" size="small" @click="handleGetStats" :loading="loading">
          刷新
        </el-button>
      </template>
      <div class="stats-grid">
        <div class="stat-item">
          <el-icon name="FileText" class="stat-icon" />
          <div class="stat-info">
            <span class="stat-value">{{ stats?.document_count || 0 }}</span>
            <span class="stat-label">文档总数</span>
          </div>
        </div>
        <div class="stat-item">
          <el-icon name="PieChart" class="stat-icon" />
          <div class="stat-info">
            <span class="stat-value">{{ stats?.total_chunks || 0 }}</span>
            <span class="stat-label">总片段数</span>
          </div>
        </div>
        <div class="stat-item">
          <el-icon name="HardDrive" class="stat-icon" />
          <div class="stat-info">
            <span class="stat-value">{{ formatSize(stats?.total_size || 0) }}</span>
            <span class="stat-label">总大小（MB）</span>
          </div>
        </div>
      </div>
    </el-card>

    <el-card shadow="never" class="upload-card">
      <template #header>
        <span class="section-title">上传制度与监管文件</span>
      </template>
      <el-upload
        ref="uploadRef"
        drag
        action="#"
        :auto-upload="false"
        :on-change="handleFileSelect"
        accept=".docx,.doc,.pdf,.txt,.md,.csv,.xlsx,.xls"
        :limit="1"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          拖拽文件到此处，或 <em>点击选择文件</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持: pdf, docx, doc, txt, md, csv, xlsx, xls；建议包含制度编号、版本和生效日期
          </div>
        </template>
      </el-upload>
    </el-card>

    <el-card shadow="never" class="document-list-card">
      <template #header>
        <span class="section-title">制度文件清单</span>
        <el-button type="primary" size="small" @click="handleRefreshDocuments" :loading="loading">
          刷新列表
        </el-button>
      </template>
      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          placeholder="搜索文档名称..."
          prefix-icon="Search"
          clearable
        />
      </div>
      <el-table
        :data="filteredDocuments"
        border
        :loading="loading"
      >
        <el-table-column
          prop="name"
          label="文档名称"
        />
        <el-table-column
          prop="chunks_count"
          label="片段数"
        />
        <el-table-column
          prop="size"
          label="文件大小"
          :formatter="formatFileSize"
        />
        <el-table-column
          prop="upload_time"
          label="上传时间"
          :formatter="formatUploadTime"
        />
        <el-table-column
          label="操作"
          width="80"
        >
          <template #default="scope">
            <el-button
              type="danger"
              size="small"
              icon="Delete"
              @click="handleDelete(scope.row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="documents.length === 0" class="empty-state">
        <el-empty description="暂无上传的文档" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { uploadDocument, getStats, getDocumentList, deleteDocument } from '../api'

const stats = ref(null)
const loading = ref(false)
const searchQuery = ref('')
const documents = ref([])
const uploadRef = ref(null)

const filteredDocuments = computed(() => {
  if (!searchQuery.value.trim()) {
    return documents.value
  }
  return documents.value.filter(doc =>
    doc.name.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
})

const formatSize = (bytes) => {
  if (bytes === 0) return '0'
  return (bytes / (1024 * 1024)).toFixed(2)
}

const formatFileSize = (row) => {
  return formatSize(row.size) + ' MB'
}

const formatUploadTime = (row) => {
  const timestamp = row.upload_time
  if (!timestamp) return '-'
  const date = new Date(timestamp * 1000)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
}

const handleGetStats = async () => {
  loading.value = true
  try {
    const result = await getStats()
    stats.value = {
      document_count: result?.vector_store?.documents || documents.value.length,
      total_chunks: result?.vector_store?.total_chunks || documents.value.reduce((sum, doc) => sum + (doc.chunks_count || 0), 0),
      total_size: result?.vector_store?.total_size || documents.value.reduce((sum, doc) => sum + (doc.size || 0), 0)
    }
  } catch (err) {
    ElMessage.error('获取统计失败: ' + (err.response?.data?.detail || err.message))
    stats.value = {
      document_count: documents.value.length,
      total_chunks: documents.value.reduce((sum, doc) => sum + (doc.chunks_count || 0), 0),
      total_size: documents.value.reduce((sum, doc) => sum + (doc.size || 0), 0)
    }
  } finally {
    loading.value = false
  }
}

const handleRefreshDocuments = async () => {
  loading.value = true
  try {
    const result = await getDocumentList()
    documents.value = result || []
    handleGetStats()
  } catch (err) {
    ElMessage.error('获取文档列表失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

const handleFileSelect = async (file) => {
  loading.value = true
  try {
    const result = await uploadDocument(file.raw)
    ElMessage.success('上传成功')
    handleRefreshDocuments()
    if (uploadRef.value) {
      uploadRef.value.clearFiles()
    }
  } catch (err) {
    ElMessage.error('上传失败: ' + (err.response?.data?.detail || err.message))
    if (uploadRef.value) {
      uploadRef.value.clearFiles()
    }
  } finally {
    loading.value = false
  }
}

const handleDelete = (row) => {
  ElMessageBox.confirm(
    '确定要删除该文档吗？',
    '提示',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    loading.value = true
    try {
      await deleteDocument(row.id)
      const index = documents.value.findIndex(doc => doc.id === row.id)
      if (index > -1) {
        documents.value.splice(index, 1)
      }
      ElMessage.success('删除成功')
      handleGetStats()
    } catch (err) {
      ElMessage.error('删除失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      loading.value = false
    }
  }).catch(() => {
    ElMessage.info('已取消删除')
  })
}

onMounted(() => {
  handleRefreshDocuments()
})
</script>

<style scoped>
.knowledge-base {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.section-title {
  font-weight: 600;
  font-size: 16px;
}

.stats-card {
  padding: 16px;
}

.stats-grid {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  background: var(--el-fill-color-light, #f8f9fa);
  border-radius: 8px;
  min-width: 200px;
}

.stat-icon {
  font-size: 28px;
  color: var(--el-color-primary, #409eff);
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.stat-label {
  font-size: 14px;
  color: var(--el-text-color-secondary, #909399);
}

.upload-card {
  padding: 16px;
}

.document-list-card {
  padding: 16px;
}

.search-bar {
  margin-bottom: 16px;
}

.empty-state {
  padding: 40px;
}
</style>
