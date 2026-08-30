<template>
  <div class="personality-settings">
    <h2>AI个性设置</h2>

    <el-card shadow="never" class="personality-card">
      <template #header>
        <span class="card-title">个性参数调整</span>
      </template>

      <el-form :model="personalityForm" label-width="120px" label-position="left">
        <el-form-item label="温暖度">
          <el-slider
            v-model="personalityForm.warmth"
            :min="0"
            :max="100"
            show-input
          ></el-slider>
          <span class="param-description">控制AI回应的亲和力和情感温度</span>
        </el-form-item>

        <el-form-item label="专业度">
          <el-slider
            v-model="personalityForm.expertise"
            :min="0"
            :max="100"
            show-input
          ></el-slider>
          <span class="param-description">控制AI回应的专业性和技术深度</span>
        </el-form-item>

        <el-form-item label="幽默感">
          <el-slider
            v-model="personalityForm.humor"
            :min="0"
            :max="100"
            show-input
          ></el-slider>
          <span class="param-description">控制AI回应中幽默元素的比例</span>
        </el-form-item>

        <el-form-item label="共情能力">
          <el-slider
            v-model="personalityForm.empathy"
            :min="0"
            :max="100"
            show-input
          ></el-slider>
          <span class="param-description">控制AI对用户情感的理解和回应</span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="savePersonality" :loading="loading">
            保存设置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getPersonality, updatePersonality } from '../api'

const personalityForm = ref({
  user_id: 'default_user',
  warmth: 50,
  expertise: 50,
  humor: 50,
  empathy: 50
})
const loading = ref(false)

const loadPersonality = async () => {
  try {
    loading.value = true
    const data = await getPersonality('default_user')
    personalityForm.value = {
      user_id: 'default_user',
      warmth: data.warmth,
      expertise: data.expertise,
      humor: data.humor,
      empathy: data.empathy
    }
  } catch (error) {
    ElMessage.error('获取个性参数失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const savePersonality = async () => {
  try {
    loading.value = true
    await updatePersonality({
      user_id: personalityForm.value.user_id,
      warmth: personalityForm.value.warmth,
      expertise: personalityForm.value.expertise,
      humor: personalityForm.value.humor,
      empathy: personalityForm.value.empathy
    })
    ElMessage.success('个性参数保存成功')
  } catch (error) {
    ElMessage.error('保存个性参数失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadPersonality()
})
</script>

<style scoped>
.personality-settings {
  padding: 20px;
}

.personality-card {
  margin-bottom: 20px;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.param-description {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
}

.el-form-item {
  margin-bottom: 24px;
}
</style>