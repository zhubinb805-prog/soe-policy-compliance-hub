<template>
  <div class="api-demo">
    <el-card shadow="never">
      <template #header>
        <span>健康检查</span>
      </template>
      <el-button type="primary" :loading="loading" @click="handleHealthCheck">
        检查健康状态
      </el-button>

      <el-result
        v-if="healthStatus"
        :icon="healthStatus.status === 'ok' ? 'success' : 'error'"
        :title="healthStatus.status === 'ok' ? '系统运行正常' : '系统异常'"
        :sub-title="'服务: ' + healthStatus.service"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { healthCheck } from '../api'

const healthStatus = ref(null)
const loading = ref(false)

const handleHealthCheck = async () => {
  loading.value = true
  healthStatus.value = null
  try {
    healthStatus.value = await healthCheck()
    ElMessage.success('健康检查完成')
  } catch (err) {
    ElMessage.error('健康检查失败: 无法连接到服务器')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.api-demo {
  width: 100%;
}
</style>
