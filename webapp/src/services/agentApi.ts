import axios from 'axios'
import type {
  AgentModel,
  AgentSession,
  AgentMessage,
  ChatRequest,
  ChatResponse,
  CreateSessionRequest,
  ModelProvider
} from '../types'

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

export const agentApi = {
  // Получить доступные модели для провайдера
  async getAvailableModels(provider: ModelProvider): Promise<AgentModel[]> {
    const response = await axios.get(`${API_BASE}/agent/models/${provider}`)
    return response.data
  },

  // Создать новую сессию
  async createSession(request: CreateSessionRequest): Promise<AgentSession> {
    const response = await axios.post(`${API_BASE}/agent/sessions`, request)
    return response.data
  },

  // Получить список сессий пользователя
  async getUserSessions(limit: number = 20): Promise<{ sessions: AgentSession[]; total: number }> {
    const response = await axios.get(`${API_BASE}/agent/sessions`, {
      params: { limit }
    })
    return response.data
  },

  // Получить информацию о сессии
  async getSession(sessionId: string): Promise<AgentSession> {
    const response = await axios.get(`${API_BASE}/agent/sessions/${sessionId}`)
    return response.data
  },

  // Получить сообщения сессии
  async getSessionMessages(sessionId: string): Promise<AgentMessage[]> {
    const response = await axios.get(`${API_BASE}/agent/sessions/${sessionId}/messages`)
    return response.data
  },

  // Отправить сообщение агенту
  async sendMessage(sessionId: string, message: ChatRequest): Promise<ChatResponse> {
    const response = await axios.post(`${API_BASE}/agent/sessions/${sessionId}/chat`, message)
    return response.data
  },

  // Удалить сессию
  async deleteSession(sessionId: string): Promise<{ message: string }> {
    const response = await axios.delete(`${API_BASE}/agent/sessions/${sessionId}`)
    return response.data
  }
}
