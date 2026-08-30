import { ref } from 'vue'

const VALID_CREDENTIALS = { username: 'admin', password: 'admin123' }
const AUTH_TOKEN_KEY = 'auth_token'
const AUTH_USER_KEY = 'auth_user'

const isLoggedIn = ref(false)
const currentUser = ref(null)

const storedToken = localStorage.getItem(AUTH_TOKEN_KEY)
const storedUser = localStorage.getItem(AUTH_USER_KEY)
if (storedToken && storedUser) {
  isLoggedIn.value = true
  currentUser.value = storedUser
}

export function useAuth() {
  const login = (username, password) => {
    if (username === VALID_CREDENTIALS.username && password === VALID_CREDENTIALS.password) {
      const mockToken = 'mock_' + Date.now() + '_' + Math.random().toString(36).substring(2, 10)
      localStorage.setItem(AUTH_TOKEN_KEY, mockToken)
      localStorage.setItem(AUTH_USER_KEY, username)
      isLoggedIn.value = true
      currentUser.value = username
      return { success: true }
    }
    return { success: false, error: '用户名或密码错误' }
  }

  const logout = () => {
    localStorage.removeItem(AUTH_TOKEN_KEY)
    localStorage.removeItem(AUTH_USER_KEY)
    isLoggedIn.value = false
    currentUser.value = null
  }

  const getToken = () => localStorage.getItem(AUTH_TOKEN_KEY)

  return { isLoggedIn, currentUser, login, logout, getToken }
}
