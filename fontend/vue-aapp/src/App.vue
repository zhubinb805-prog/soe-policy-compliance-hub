<template>
  <div id="app">
    <template v-if="isLoggedIn">
      <header class="app-header">
        <div class="header-left">
          <h1 class="app-title">央国企制度与合规知识库</h1>
        </div>
        <div class="header-right">
          <el-dropdown trigger="click">
            <span class="nav-item">
              <el-icon name="Setting" />
              <span>设置</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="currentNav = 'memory'">
                  <el-icon name="User" /> 用户画像
                </el-dropdown-item>
                <el-dropdown-item @click="currentNav = 'chat'">
                  <el-icon name="ChatLineRound" /> AI个性
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>

          <el-tooltip :content="isDark ? '切换浅色模式' : '切换深色模式'" placement="bottom">
            <el-button
              :icon="isDark ? Sunny : Moon"
              circle
              text
              @click="toggleTheme"
              class="theme-btn"
            />
          </el-tooltip>

          <el-dropdown trigger="click">
            <span class="user-info">
              <el-avatar :size="28" class="user-avatar">
                {{ currentUser?.charAt(0).toUpperCase() }}
              </el-avatar>
              <span class="user-name">{{ currentUser }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleLogout" :icon="SwitchButton">
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <nav class="main-nav">
        <div class="nav-container">
          <div
            v-for="item in navItems"
            :key="item.key"
            :class="['nav-item-box', { active: currentNav === item.key }]"
            @click="currentNav = item.key"
          >
            <el-icon :name="item.icon" class="nav-icon" />
            <span class="nav-text">{{ item.label }}</span>
          </div>
        </div>
      </nav>

      <main class="app-main">
        <component :is="currentComponent" />
      </main>
    </template>

    <template v-else>
      <LoginPage />
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Sunny, Moon, ArrowDown, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import ApiDemo from './components/ApiDemo.vue'
import ProfileSettings from './components/ProfileSettings.vue'
import PersonalitySettings from './components/PersonalitySettings.vue'
import LoginPage from './components/LoginPage.vue'
import ConversationWorkbench from './components/ConversationWorkbench.vue'
import KnowledgeBase from './components/KnowledgeBase.vue'
import ConversationManager from './components/ConversationManager.vue'
import CompliancePrecheck from './components/CompliancePrecheck.vue'
import { useAuth } from './composables/useAuth'
import { useTheme } from './composables/useTheme'

const { isLoggedIn, currentUser, logout } = useAuth()
const { isDark, toggle: toggleTheme } = useTheme()

const currentNav = ref('workbench')

const navItems = [
  { key: 'workbench', label: '对话工作台', icon: 'MessageSquare' },
  { key: 'conversations', label: '会话管理', icon: 'Message' },
  { key: 'knowledge', label: '制度知识库', icon: 'BookOpen' },
  { key: 'precheck', label: '合规预审', icon: 'Checked' },
]

const currentComponent = computed(() => {
  switch (currentNav.value) {
    case 'workbench':
      return ConversationWorkbench
    case 'conversations':
      return ConversationManager
    case 'knowledge':
      return KnowledgeBase
    case 'precheck':
      return CompliancePrecheck
    case 'memory':
      return ProfileSettings
    case 'chat':
      return PersonalitySettings
    default:
      return ConversationWorkbench
  }
})

const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    logout()
  }).catch(() => {})
}
</script>

<style>
#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
  background: var(--background-color, #f5f7fa);
  color: var(--page-text-color, #303133);
  transition: background 0.3s, color 0.3s;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 60px;
  background: var(--el-bg-color, #ffffff);
  border-bottom: 1px solid var(--el-border-color, #e4e7ed);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 0;
  z-index: 100;
  transition: background 0.3s, border-color 0.3s;
}

.app-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.theme-btn {
  font-size: 18px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--el-text-color-regular, #606266);
  font-size: 14px;
}

.user-avatar {
  background: #409eff;
  color: white;
}

.main-nav {
  background: var(--el-bg-color, #ffffff);
  border-bottom: 1px solid var(--el-border-color, #e4e7ed);
  padding: 12px 24px;
}

.nav-container {
  display: flex;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
}

.nav-item-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--el-fill-color-light, #f8f9fa);
  border: 1px solid transparent;
  text-align: center;
  width: 140px;
}

.nav-item-box:hover {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.nav-item-box.active {
  background: var(--el-color-primary, #409eff);
  color: #ffffff;
  border-color: var(--el-color-primary, #409eff);
}

.nav-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.nav-text {
  font-size: 14px;
  font-weight: 500;
  text-align: center;
  flex: 1;
  margin: 0;
}

.app-main {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}
</style>
