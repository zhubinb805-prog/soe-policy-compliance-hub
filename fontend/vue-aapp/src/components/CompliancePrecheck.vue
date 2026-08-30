<template>
  <div class="precheck-page">
    <div class="page-heading">
      <div>
        <h2>采购合规预审</h2>
        <p>基于制度阈值生成可解释的审批路径与风险提示</p>
      </div>
      <el-tag type="success" effect="plain">规则版本 CG-2026-001 / V2.1</el-tag>
    </div>

    <section class="form-section">
      <el-form label-position="top" @submit.prevent="runCheck">
        <div class="form-grid">
          <el-form-item label="采购金额（元）">
            <el-input-number v-model="amount" :min="0" :step="100000" controls-position="right" />
          </el-form-item>
          <el-form-item label="适用组织范围">
            <el-select v-model="scope">
              <el-option label="集团总部及所属全资、控股子公司" value="集团总部及所属全资、控股子公司" />
              <el-option label="集团总部" value="集团总部" />
              <el-option label="所属子公司" value="所属子公司" />
            </el-select>
          </el-form-item>
        </div>
        <el-button type="primary" :loading="loading" @click="runCheck">执行预审</el-button>
      </el-form>
    </section>

    <template v-if="result">
      <section class="result-band">
        <div class="result-amount">
          <span>本次采购金额</span>
          <strong>¥ {{ formatAmount(result.amount) }}</strong>
        </div>
        <div class="next-action">
          <span>建议下一步</span>
          <strong>{{ result.next_action }}</strong>
        </div>
      </section>

      <div class="result-grid">
        <section>
          <h3>审批路径</h3>
          <el-steps direction="vertical" :active="result.required_steps.length" finish-status="success">
            <el-step v-for="step in result.required_steps" :key="step" :title="step" />
          </el-steps>
        </section>
        <section>
          <h3>风险红线</h3>
          <el-alert v-for="risk in result.risk_flags" :key="risk" :title="risk" type="warning" :closable="false" show-icon />
          <h3 class="basis-title">制度依据</h3>
          <div v-for="item in result.basis" :key="item" class="basis-item">{{ item }}</div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { procurementComplianceCheck } from '../api'

const amount = ref(1200000)
const scope = ref('集团总部及所属全资、控股子公司')
const loading = ref(false)
const result = ref(null)

const formatAmount = value => Number(value).toLocaleString('zh-CN', { minimumFractionDigits: 2 })

const runCheck = async () => {
  loading.value = true
  try {
    result.value = await procurementComplianceCheck({ amount: amount.value, scope: scope.value })
  } catch (error) {
    ElMessage.error('预审失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.precheck-page { max-width: 1040px; margin: 0 auto; }
.page-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
.page-heading h2 { margin: 0 0 6px; font-size: 24px; }
.page-heading p { margin: 0; color: #606266; }
.form-section { padding: 24px; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.el-input-number, .el-select { width: 100%; }
.result-band { display: grid; grid-template-columns: 240px 1fr; margin-top: 20px; border: 1px solid #b7dfc4; background: #f1f9f3; }
.result-band > div { padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.result-amount { border-right: 1px solid #b7dfc4; }
.result-band span { color: #606266; font-size: 13px; }
.result-band strong { font-size: 17px; color: #1f5132; }
.result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 20px; }
.result-grid section { padding: 24px; background: #fff; border: 1px solid #e4e7ed; }
.result-grid h3 { margin: 0 0 18px; font-size: 16px; }
.el-alert { margin-bottom: 12px; }
.basis-title { margin-top: 26px !important; }
.basis-item { padding: 12px 14px; margin-bottom: 8px; background: #f5f7fa; border-left: 3px solid #409eff; font-size: 14px; }
@media (max-width: 720px) {
  .page-heading, .result-band { display: flex; flex-direction: column; align-items: flex-start; gap: 12px; }
  .form-grid, .result-grid { grid-template-columns: 1fr; }
  .result-amount { border-right: 0; border-bottom: 1px solid #b7dfc4; width: 100%; box-sizing: border-box; }
}
</style>
