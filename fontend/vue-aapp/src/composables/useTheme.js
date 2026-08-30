import { ref, watch } from 'vue'

const THEME_KEY = 'theme_preference'
const stored = localStorage.getItem(THEME_KEY)
const initial = stored || 'light'

const isDark = ref(initial === 'dark')

const lightVars = {
  '--el-bg-color': '#ffffff',
  '--el-bg-color-page': '#f5f7fa',
  '--el-text-color-primary': '#303133',
  '--el-text-color-regular': '#606266',
  '--el-border-color': '#dcdfe6',
  '--el-fill-color-blank': '#ffffff',
  '--el-fill-color': '#f0f2f5',
  '--background-color': '#f5f7fa',
  '--card-bg': '#ffffff',
  '--page-text-color': '#303133',
}

const darkVars = {
  '--el-bg-color': '#1d1e1f',
  '--el-bg-color-page': '#0a0a0a',
  '--el-text-color-primary': '#e5eaf3',
  '--el-text-color-regular': '#cfd3dc',
  '--el-border-color': '#4c4d4f',
  '--el-fill-color-blank': '#1d1e1f',
  '--el-fill-color': '#262727',
  '--background-color': '#0a0a0a',
  '--card-bg': '#1d1e1f',
  '--page-text-color': '#e5eaf3',
}

function applyTheme(dark) {
  const vars = dark ? darkVars : lightVars
  const root = document.documentElement
  Object.entries(vars).forEach(([key, value]) => {
    root.style.setProperty(key, value)
  })
  document.documentElement.classList.toggle('dark', dark)
}

applyTheme(isDark.value)

export function useTheme() {
  const toggle = () => {
    isDark.value = !isDark.value
  }

  watch(isDark, (val) => {
    applyTheme(val)
    localStorage.setItem(THEME_KEY, val ? 'dark' : 'light')
  })

  return { isDark, toggle }
}
