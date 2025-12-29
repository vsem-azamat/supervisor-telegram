import type { Chat, BulkActionConfig, BulkExecutionResult } from '../types'

// Mock chat data
export const mockChatsData: Chat[] = [
  {
    id: 1,
    title: 'Programming in Czechia',
    type: 'supergroup',
    member_count: 15420,
    description: 'Chat for IT specialists in the Czech Republic',
    welcome_message: 'Welcome to the programmer community! 🚀',
    auto_delete_welcome_delay: 300,
    is_active: true,
    created_at: '2023-01-15T10:00:00Z',
    updated_at: '2024-12-19T14:30:00Z'
  },
  {
    id: 2,
    title: 'Learning Czech Language',
    type: 'group',
    member_count: 8750,
    description: 'Learning Czech for Russian speakers',
    welcome_message: 'Dobrý den! Welcome to the language group! 🇨🇿',
    is_active: true,
    created_at: '2023-03-20T15:20:00Z',
    updated_at: '2024-12-18T09:15:00Z'
  },
  {
    id: 3,
    title: 'Jobs in Prague',
    type: 'supergroup',
    member_count: 23100,
    description: 'Job search and vacancies in Prague',
    welcome_message: 'Welcome! Find your dream job in Prague here 💼',
    auto_delete_welcome_delay: 600,
    is_active: true,
    created_at: '2023-02-10T12:45:00Z',
    updated_at: '2024-12-19T16:00:00Z'
  },
  {
    id: 4,
    title: 'Students in Czechia',
    type: 'group',
    member_count: 5640,
    description: 'Community for students and applicants',
    welcome_message: 'Hello, student! 🎓 Find all necessary info here!',
    is_active: false,
    created_at: '2023-05-12T08:30:00Z',
    updated_at: '2024-11-20T11:45:00Z'
  },
  {
    id: 5,
    title: 'IT News Czechia',
    type: 'channel',
    member_count: 12890,
    description: 'Latest IT news in the Czech Republic',
    is_active: true,
    created_at: '2023-04-01T14:20:00Z',
    updated_at: '2024-12-19T10:30:00Z'
  },
  {
    id: 6,
    title: 'Housing Search Prague',
    type: 'supergroup',
    member_count: 18500,
    description: 'Find or rent housing in Prague and surroundings',
    welcome_message: 'Welcome to the housing search group! 🏠',
    auto_delete_welcome_delay: 480,
    is_active: true,
    created_at: '2023-01-25T16:10:00Z',
    updated_at: '2024-12-19T12:20:00Z'
  },
  {
    id: 7,
    title: 'Cars in Czechia',
    type: 'group',
    member_count: 4200,
    description: 'Buying, selling and car maintenance',
    welcome_message: 'Welcome to the car community! 🚗',
    is_active: true,
    created_at: '2023-06-15T11:00:00Z',
    updated_at: '2024-12-17T14:45:00Z'
  },
  {
    id: 8,
    title: 'Medicine in Czechia',
    type: 'group',
    member_count: 3100,
    description: 'Medical help and insurance for foreigners',
    welcome_message: 'Hello! Find answers to medical questions here 🏥',
    is_active: false,
    created_at: '2023-07-08T13:30:00Z',
    updated_at: '2024-10-12T09:20:00Z'
  },
  {
    id: 9,
    title: 'Travel across Czechia',
    type: 'supergroup',
    member_count: 9800,
    description: 'Tourism, sights and travel',
    welcome_message: 'Welcome to the travelers community! 🗺️',
    auto_delete_welcome_delay: 300,
    is_active: true,
    created_at: '2023-08-22T17:15:00Z',
    updated_at: '2024-12-18T15:30:00Z'
  },
  {
    id: 10,
    title: 'Business in Czechia',
    type: 'group',
    member_count: 6700,
    description: 'Starting and running business in CR',
    welcome_message: 'Welcome to the business community! 💼',
    is_active: true,
    created_at: '2023-09-10T10:45:00Z',
    updated_at: '2024-12-19T11:10:00Z'
  }
]

// Mock API functions
export const mockChats = async (): Promise<Chat[]> => {
  // Simulate API delay
  await new Promise(resolve => setTimeout(resolve, 800))
  return mockChatsData
}

export const mockBulkUpdate = async (
  chatIds: number[],
  config: BulkActionConfig
): Promise<BulkExecutionResult> => {
  // Simulate API processing time
  await new Promise(resolve => setTimeout(resolve, 2000))

  // Simulate some failures (10% failure rate)
  const results = chatIds.map(chatId => {
    const chat = mockChatsData.find(c => c.id === chatId)
    const success = Math.random() > 0.1 // 90% success rate

    return {
      chatId,
      chatTitle: chat?.title || `Chat ${chatId}`,
      success,
      error: success ? undefined : 'Temporary Telegram API error',
      changes: success ? config.values : undefined
    }
  })

  const successCount = results.filter(r => r.success).length
  const failureCount = results.length - successCount

  return {
    success: failureCount === 0,
    totalChats: chatIds.length,
    successCount,
    failureCount,
    results
  }
}

// Export mock stats for future analytics
export const mockChatStats = {
  totalChats: mockChatsData.length,
  activeChats: mockChatsData.filter(c => c.is_active).length,
  totalMembers: mockChatsData.reduce((sum, chat) => sum + (chat.member_count || 0), 0),
  averageMembers: Math.round(
    mockChatsData.reduce((sum, chat) => sum + (chat.member_count || 0), 0) / mockChatsData.length
  ),
  chatsByType: mockChatsData.reduce((acc, chat) => {
    acc[chat.type] = (acc[chat.type] || 0) + 1
    return acc
  }, {} as Record<string, number>)
}
