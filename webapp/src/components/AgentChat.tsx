import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  Paper, Stack, Group, Text, Button, Textarea, Select, Box,
  ScrollArea, Loader, Alert, Title, Badge
} from '@mantine/core'
import { agentApi } from '../services/agentApi'
import { MarkdownContent } from './MarkdownContent'
import type {
  AgentSession,
  AgentMessage,
  AgentModel,
  CreateSessionRequest
} from '../types'

interface AgentChatProps {
  session?: AgentSession
  onSessionCreate?: (session: AgentSession) => void
}

export const AgentChat: React.FC<AgentChatProps> = ({
  session: initialSession,
  onSessionCreate
}) => {
  const [session, setSession] = useState<AgentSession | null>(initialSession || null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showModelSelector, setShowModelSelector] = useState(false)
  const [availableModels, setAvailableModels] = useState<{
    openai: AgentModel[]
    openrouter: AgentModel[]
  }>({ openai: [], openrouter: [] })
  const [selectedModel, setSelectedModel] = useState<AgentModel | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadAvailableModels = useCallback(async () => {
    try {
      const [openaiModels, openrouterModels] = await Promise.all([
        agentApi.getAvailableModels('openai'),
        agentApi.getAvailableModels('openrouter')
      ])
      setAvailableModels({
        openai: openaiModels,
        openrouter: openrouterModels
      })
      // Default to first OpenRouter model (Claude 3.5 Sonnet is usually first)
      if (openrouterModels.length > 0) {
        setSelectedModel(openrouterModels[0])
      } else if (openaiModels.length > 0) {
        setSelectedModel(openaiModels[0])
      }
    } catch (err) {
      setError('Ошибка при загрузке моделей')
      console.error(err)
    }
  }, [])

  const loadMessages = useCallback(async () => {
    if (!session) return

    try {
      const msgs = await agentApi.getSessionMessages(session.id)
      setMessages(msgs)
    } catch (err) {
      setError('Ошибка при загрузке сообщений')
      console.error(err)
    }
  }, [session])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (session) {
      loadMessages()
    }
  }, [session, loadMessages])

  useEffect(() => {
    if (!session) {
      setShowModelSelector(true)
      loadAvailableModels()
    }
  }, [session, loadAvailableModels])

  const createSession = async () => {
    if (!selectedModel) {
      setError('Выберите модель')
      return
    }

    try {
      const createRequest: CreateSessionRequest = {
        agent_config: {
          provider: selectedModel.provider,
          model_id: selectedModel.model_id,
          model_name: selectedModel.model_name,
          temperature: selectedModel.temperature,
          max_tokens: selectedModel.max_tokens
        },
        title: `Чат с ${selectedModel.model_name}`
      }

      const newSession = await agentApi.createSession(createRequest)
      setSession(newSession)
      setShowModelSelector(false)
      onSessionCreate?.(newSession)
    } catch (err) {
      setError('Ошибка при создании сессии')
      console.error(err)
    }
  }

  const sendMessage = async () => {
    if (!newMessage.trim() || !session || isLoading) return

    const userMessage: AgentMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: newMessage,
      timestamp: new Date().toISOString()
    }

    setMessages(prev => [...prev, userMessage])
    setNewMessage('')
    setIsLoading(true)
    setError(null)

    try {
      const response = await agentApi.sendMessage(session.id, { message: newMessage })

      const assistantMessage: AgentMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: response.timestamp
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (err) {
      setError('Ошибка при отправке сообщения')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  if (showModelSelector) {
    return (
      <Paper shadow="xs" p="xl" withBorder>
        <Stack gap="md">
          <Title order={2} ta="center">🤖 Создать сессию с AI агентом</Title>

          <Select
            label="Модель"
            value={selectedModel?.model_id || ''}
            onChange={(value) => {
              const model = availableModels.openrouter.find(m => m.model_id === value)
              setSelectedModel(model || null)
            }}
            data={availableModels.openrouter.map(model => ({
              value: model.model_id,
              label: `${model.model_name}${model.max_tokens ? ` (${model.max_tokens} tokens)` : ''}`
            }))}
          />

          {selectedModel && (
            <Paper p="md" withBorder bg="gray.0">
              <Text size="sm" c="dimmed">{selectedModel.description}</Text>
            </Paper>
          )}

          <Button
            onClick={createSession}
            disabled={!selectedModel}
            size="lg"
            leftSection={<span>✨</span>}
          >
            Создать сессию
          </Button>
        </Stack>
      </Paper>
    )
  }

  return (
    <Paper shadow="xs" withBorder style={{ display: 'flex', flexDirection: 'column', height: '600px' }}>
      {/* Chat Header */}
      <Box p="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
        <Group justify="space-between">
          <Text fw={600} size="lg">🤖 {session?.title || 'AI Агент'}</Text>
          {session && (
            <Group gap="md">
              <Text size="sm" c="dimmed">
                {session.agent_config.model_name}
              </Text>
              <Badge size="sm" variant="light">
                {session.agent_config.provider}
              </Badge>
              <Text size="sm" c="dimmed">
                {messages.length} сообщений
              </Text>
            </Group>
          )}
        </Group>
      </Box>

      {/* Messages Container */}
      <ScrollArea style={{ flex: 1 }} p="md">
        <Stack gap="md">
          {messages.map((message) => (
            <Paper
              key={message.id}
              p="md"
              withBorder={message.role === 'assistant'}
              style={{
                backgroundColor: message.role === 'user'
                  ? 'var(--mantine-color-blue-6)'
                  : 'var(--mantine-color-gray-0)',
                color: message.role === 'user'
                  ? 'white'
                  : 'var(--mantine-color-dark-9)',
                marginLeft: message.role === 'user' ? '2rem' : '0',
                marginRight: message.role === 'assistant' ? '2rem' : '0',
                borderRadius: '12px'
              }}
            >
              <Group justify="space-between" mb="xs">
                <Text size="sm" fw={600}>
                  {message.role === 'user' ? '👤 Вы' : '🤖 Агент'}
                </Text>
                <Text size="xs" opacity={0.7}>
                  {new Date(message.timestamp).toLocaleTimeString()}
                </Text>
              </Group>
              {message.role === 'assistant' ? (
                <MarkdownContent content={message.content} />
              ) : (
                <Text style={{ whiteSpace: 'pre-wrap', lineHeight: 1.4 }}>
                  {message.content}
                </Text>
              )}
            </Paper>
          ))}

          {isLoading && (
            <Paper p="md" withBorder style={{ marginRight: '2rem', borderRadius: '12px' }}>
              <Group mb="xs">
                <Text size="sm" fw={600}>🤖 Агент</Text>
                <Text size="xs" c="dimmed">Печатает...</Text>
              </Group>
              <Group gap="xs">
                <Loader size="xs" />
                <Text size="sm" c="dimmed">Думаю...</Text>
              </Group>
            </Paper>
          )}

          <div ref={messagesEndRef} />
        </Stack>
      </ScrollArea>

      {/* Error Alert */}
      {error && (
        <Box p="md">
          <Alert
            color="red"
            title="⚠️ Ошибка"
            withCloseButton
            onClose={() => setError(null)}
          >
            {error}
          </Alert>
        </Box>
      )}

      {/* Message Input */}
      <Box p="md" style={{ borderTop: '1px solid var(--mantine-color-gray-3)' }}>
        <Group gap="md" align="flex-end">
          <Textarea
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            onKeyDown={handleKeyPress}
            placeholder="Напишите сообщение агенту..."
            rows={3}
            disabled={isLoading}
            style={{ flex: 1 }}
          />
          <Button
            onClick={sendMessage}
            disabled={!newMessage.trim() || isLoading}
            loading={isLoading}
            size="lg"
            h={80}
          >
            {isLoading ? '⏳' : '📤'}
          </Button>
        </Group>
      </Box>
    </Paper>
  )
}
