<template>
  <div class="profile-settings">
    <h2>用户画像管理</h2>

    <el-card shadow="never" class="profile-card">
      <template #header>
        <span class="card-title">个人资料</span>
      </template>

      <el-form :model="profileForm" label-width="120px" label-position="left">
        <el-form-item label="用户ID">
          <el-input v-model="profileForm.user_id" disabled></el-input>
        </el-form-item>

        <el-form-item label="姓名">
          <el-input v-model="profileForm.name"></el-input>
        </el-form-item>

        <el-form-item label="专业背景">
          <el-input
            type="textarea"
            v-model="profileForm.background"
            :rows="3"
            placeholder="描述您的专业背景、工作经验等"
          ></el-input>
        </el-form-item>

        <el-form-item label="偏好设置">
          <el-input
            type="textarea"
            v-model="profileForm.preferences_str"
            :rows="4"
            placeholder="JSON格式的偏好设置，例如：{&quot;topic&quot;: &quot;技术&quot;, &quot;style&quot;: &quot;简洁&quot;}"
          ></el-input>
        </el-form-item>

        <el-form-item label="交互次数">
          <el-input v-model="profileForm.interaction_count" disabled></el-input>
        </el-form-item>

        <el-form-item label="最后活跃">
          <el-input v-model="profileForm.last_active" disabled></el-input>
        </el-form-item>

        <el-form-item label="创建时间">
          <el-input v-model="profileForm.created_at" disabled></el-input>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="saveProfile" :loading="loading">
            保存资料
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getUserProfile, updateUserProfile } from '../api'
const profileForm = ref({
  user_id: 'default_user',
  name: '',
  background: '',
  preferences: {},
  preferences_str: '{}',
  interaction_count: 0,
  last_active: '',
  created_at: ''
})
const loading = ref(false)

const loadProfile = async () => {
  try {
    loading.value = true
    const data = await getUserProfile('default_user')
    profileForm.value = {
      ...data,
      preferences_str: JSON.stringify(data.preferences || {}, null, 2)
    }
  } catch (error) {
    ElMessage.error('获取用户画像失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const saveProfile = async () => {
  try {
    // 验证JSON格式
    let preferences = {}
    try {
      preferences = JSON.parse(profileForm.value.preferences_str)
    } catch (e) {
      ElMessage.error('偏好设置JSON格式不正确')
      return
    }

    loading.value = true
    const result = await updateUserProfile({
      user_id: profileForm.value.user_id,
      name: profileForm.value.name,
      background: profileForm.value.background,
      preferences: preferences
    })

    ElMessage.success('用户画像保存成功')
    profileForm.value = {
      ...result,
      preferences_str: JSON.stringify(result.preferences || {}, null, 2)
    }
  } catch (error) {
    ElMessage.error('保存用户画像失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadProfile()
})
</script>

<style scoped>
.profile-settings {
  padding: 20px;
}

.profile-card {
  margin-bottom: 20px;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.el-form-item {
  margin-bottom: 16px;
}

.el-input[disabled] {
  background-color: var(--el-fill-color-light);
}
</style>