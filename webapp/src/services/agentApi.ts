import apiClient from './apiClient'
import type {
  AgentModel,
  AgentSession,
  AgentMessage,
  ChatRequest,
  ChatResponse,
  CreateSessionRequest,
  ModelProvider
} from '../types'

export const agentApi = {
  // Получить доступные модели для провайдера
  async getAvailableModels(provider: ModelProvider): Promise<AgentModel[]> {
    const response = await apiClient.get(`/agent/models/${provider}`)
    return response.data
  },

  // Создать новую сессию
  async createSession(request: CreateSessionRequest): Promise<AgentSession> {
    const response = await apiClient.post(`/agent/sessions`, request)
    return response.data
  },

  // Получить список сессий пользователя
  async getUserSessions(limit: number = 20): Promise<{ sessions: AgentSession[]; total: number }> {
    const response = await apiClient.get(`/agent/sessions`, {
      params: { limit }
    })
    return response.data
  },

  // Получить информацию о сессии
  async getSession(sessionId: string): Promise<AgentSession> {
    const response = await apiClient.get(`/agent/sessions/${sessionId}`)
    return response.data
  },

  // Получить сообщения сессии
  async getSessionMessages(sessionId: string): Promise<AgentMessage[]> {
    const response = await apiClient.get(`/agent/sessions/${sessionId}/messages`)
    return response.data
  },

  // Отправить сообщение агенту
  async sendMessage(sessionId: string, message: ChatRequest): Promise<ChatResponse> {
    const response = await apiClient.post(`/agent/sessions/${sessionId}/chat`, message)
    return response.data
  },

  // Удалить сессию
  async deleteSession(sessionId: string): Promise<{ message: string }> {
    const response = await apiClient.delete(`/agent/sessions/${sessionId}`)
    return response.data
  }
}
