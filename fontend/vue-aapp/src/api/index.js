import axios from 'axios'
import { useAuth } from '../composables/useAuth'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json'
  }
})

api.interceptors.request.use(
  config => {
    const { getToken } = useAuth()
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

api.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    if (error.response?.status === 401) {
      const { logout } = useAuth()
      logout()
      window.location.reload()
    }
    return Promise.reject(error)
  }
)

export const uploadDocument = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/ingest/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000
  })
}

export const uploadBatch = (files) => {
  const formData = new FormData()
  files.forEach(file => {
    formData.append('files', file)
  })
  return api.post('/ingest/batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000
  })
}

export const askQuestion = (question, context = {}) => {
  return api.post('/qa/ask', { question, ...context })
}

export const procurementComplianceCheck = (data) => {
  return api.post('/compliance/procurement-check', data)
}

export const getStats = () => {
  return api.get('/admin/stats')
}

export const triggerUpdate = (filePath, changeType = 'modified') => {
  return api.post('/admin/update', { file_path: filePath, change_type: changeType })
}

export const healthCheck = () => {
  return api.get('/health')
}

// 记忆管理API
export const getUserProfile = async (userId) => {
  return api.get(`/memory/profile/${userId}`)
}

export const updateUserProfile = async (profileData) => {
  return api.post('/memory/profile', profileData)
}

export const getPersonality = async (userId) => {
  return api.get(`/memory/personality/${userId}`)
}

export const updatePersonality = async (personalityData) => {
  return api.post('/memory/personality', personalityData)
}

export const retrieveMemory = async (queryData) => {
  return api.post('/memory/retrieve', queryData)
}

export const getDocumentList = () => {
  return api.get('/ingest/documents')
}

export const deleteDocument = (documentId) => {
  return api.delete(`/ingest/documents/${documentId}`)
}

// 会话管理API
export const createConversation = (data) => {
  return api.post('/conversations', data)
}

export const getConversationList = (params = {}) => {
  return api.get('/conversations', { params })
}

export const getConversation = (sessionId) => {
  return api.get(`/conversations/${sessionId}`)
}

export const addMessage = (sessionId, message) => {
  return api.post(`/conversations/${sessionId}/messages`, message)
}

export const searchConversations = (data) => {
  return api.post('/conversations/search', data)
}

export const updateConversationTitle = (sessionId, title) => {
  return api.put(`/conversations/${sessionId}/title`, {}, { params: { title } })
}

export const deleteConversation = (sessionId) => {
  return api.delete(`/conversations/${sessionId}`)
}

export const deleteMessage = (sessionId, messageId) => {
  return api.delete(`/conversations/${sessionId}/messages/${messageId}`)
}

export default api
