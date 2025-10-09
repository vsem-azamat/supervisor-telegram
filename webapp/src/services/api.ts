import axios from 'axios'
import apiClient from './apiClient'
import type { Chat, BulkActionConfig, BulkExecutionResult } from '../types'

// API response types matching backend schemas
export interface ApiChatResponse {
  id: number
  title: string | null
  is_forum: boolean
  welcome_message: string | null
  welcome_delete_time: number
  is_welcome_enabled: boolean
  is_captcha_enabled: boolean
  created_at: string | null
  modified_at: string | null
}

export interface ApiChatStatsResponse {
  chat_id: number
  member_count: number
  message_count_24h: number
  active_users_24h: number
  moderation_actions_24h: number
  last_activity: string | null
}

export interface ApiBulkUpdateRequest {
  chat_ids: number[]
  update_data: {
    welcome_message?: string | null
    welcome_delete_time?: number | null
    is_welcome_enabled?: boolean | null
    is_captcha_enabled?: boolean | null
  }
}

class ApiService {
  private client: typeof apiClient

  constructor() {
    // Use shared apiClient with Telegram authentication
    this.client = apiClient
  }

  // Convert API response to frontend Chat type
  private convertApiChatToChat(apiChat: ApiChatResponse): Chat {
    return {
      id: apiChat.id,
      title: apiChat.title || `Chat ${apiChat.id}`,
      type: apiChat.is_forum ? 'supergroup' : 'group', // Simplified mapping
      member_count: undefined, // Will be fetched separately if needed
      description: undefined, // Not available in current API
      welcome_message: apiChat.welcome_message || undefined,
      auto_delete_welcome_delay: apiChat.welcome_delete_time,
      is_active: apiChat.is_welcome_enabled || apiChat.is_captcha_enabled, // Simplified logic
      created_at: apiChat.created_at || new Date().toISOString(),
      updated_at: apiChat.modified_at || new Date().toISOString()
    }
  }

  // Fetch all chats
  async getChats(): Promise<Chat[]> {
    try {
      const response = await this.client.get<ApiChatResponse[]>('/chats')
      return response.data.map(chat => this.convertApiChatToChat(chat))
    } catch (error) {
      console.error('Failed to fetch chats:', error)
      throw new Error('Не удалось загрузить чаты')
    }
  }

  // Get chat statistics
  async getChatStats(chatId: number): Promise<ApiChatStatsResponse> {
    try {
      const response = await this.client.get<ApiChatStatsResponse>(`/chats/${chatId}/stats`)
      return response.data
    } catch (error) {
      console.error(`Failed to fetch stats for chat ${chatId}:`, error)
      throw new Error(`Не удалось загрузить статистику для чата ${chatId}`)
    }
  }

  // Update single chat
  async updateChat(chatId: number, updates: Record<string, unknown>): Promise<Chat> {
    try {
      const updateData = this.convertConfigToApiUpdate(updates)
      const response = await this.client.put<ApiChatResponse>(`/chats/${chatId}`, updateData)
      return this.convertApiChatToChat(response.data)
    } catch (error) {
      console.error(`Failed to update chat ${chatId}:`, error)
      throw new Error(`Не удалось обновить чат ${chatId}`)
    }
  }

  // Bulk update chats
  async bulkUpdateChats(chatIds: number[], config: BulkActionConfig): Promise<BulkExecutionResult> {
    try {
      const updateData = this.convertConfigToApiUpdate(config.values)

      const bulkRequest: ApiBulkUpdateRequest = {
        chat_ids: chatIds,
        update_data: updateData
      }

      const response = await this.client.post<ApiChatResponse[]>('/chats/bulk-update', bulkRequest)

      // Convert to execution result format
      const results = chatIds.map(chatId => {
        const updatedChat = response.data.find(chat => chat.id === chatId)
        return {
          chatId,
          chatTitle: updatedChat?.title || `Chat ${chatId}`,
          success: !!updatedChat,
          error: updatedChat ? undefined : 'Чат не найден или не удалось обновить',
          changes: updatedChat ? config.values : undefined
        }
      })

      const successCount = results.filter(r => r.success).length

      return {
        success: successCount === chatIds.length,
        totalChats: chatIds.length,
        successCount,
        failureCount: chatIds.length - successCount,
        results
      }
    } catch (error) {
      console.error('Failed to bulk update chats:', error)

      // Return error result
      return {
        success: false,
        totalChats: chatIds.length,
        successCount: 0,
        failureCount: chatIds.length,
        results: [],
        error: 'Ошибка сервера при массовом обновлении'
      }
    }
  }

  // Convert frontend config to API update format
  private convertConfigToApiUpdate(config: Record<string, unknown>): Record<string, unknown> {
    const apiUpdate: Record<string, unknown> = {}

    // Map frontend config to API fields
    if ('description' in config) {
      // Description is not supported in current API
      console.warn('Description updates are not supported by current API')
    }

    if ('welcome_message' in config) {
      apiUpdate.welcome_message = config.welcome_message
    }

    if ('auto_delete_delay' in config) {
      apiUpdate.welcome_delete_time = config.auto_delete_delay
    }

    if ('is_active' in config) {
      // Map generic "active" to welcome enabled
      apiUpdate.is_welcome_enabled = config.is_active
    }

    if ('moderation_level' in config) {
      // Map moderation level to captcha enabled
      const level = config.moderation_level as string
      apiUpdate.is_captcha_enabled = level === 'medium' || level === 'high'
    }

    // Handle direct API field mappings
    if ('is_welcome_enabled' in config) {
      apiUpdate.is_welcome_enabled = config.is_welcome_enabled
    }

    if ('is_captcha_enabled' in config) {
      apiUpdate.is_captcha_enabled = config.is_captcha_enabled
    }

    return apiUpdate
  }

  // Health check
  async healthCheck(): Promise<boolean> {
    try {
      const response = await axios.get('/api/health')
      return response.status === 200
    } catch {
      return false
    }
  }
}

export const apiService = new ApiService()
export const chatAPI = apiService
export default apiService
