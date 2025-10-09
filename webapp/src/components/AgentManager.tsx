import React, { useState, useEffect } from 'react'
import {
  Stack, Paper, Text, Button, Group, Loader, Alert, Title,
  Badge, Box, ActionIcon, Modal
} from '@mantine/core'
import { AgentChat } from './AgentChat'
import { agentApi } from '../services/agentApi'
import type { AgentSession } from '../types'

export const AgentManager: React.FC = () => {
  const [sessions, setSessions] = useState<AgentSession[]>([])
  const [currentSession, setCurrentSession] = useState<AgentSession | null>(null)
  const [view, setView] = useState<'list' | 'chat' | 'new'>('list')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null)

  useEffect(() => {
    loadSessions()
  }, [])

  const loadSessions = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await agentApi.getUserSessions(20)
      setSessions(response.sessions)
    } catch (err) {
      if (err && typeof err === 'object' && 'response' in err && err.response && typeof err.response === 'object' && 'status' in err.response && typeof (err.response as { status?: unknown }).status === 'number' && (err.response as { status: number }).status >= 500) {
        setError('Ошибка сервера при загрузке сессий')
      } else {
        setError('Ошибка при загрузке сессий')
      }
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSessionCreate = (session: AgentSession) => {
    setSessions(prev => [session, ...prev])
    setCurrentSession(session)
    setView('chat')
  }

  const handleSessionSelect = (session: AgentSession) => {
    setCurrentSession(session)
    setView('chat')
  }

  const confirmDelete = (sessionId: string) => {
    setSessionToDelete(sessionId)
    setDeleteModalOpen(true)
  }

  const handleSessionDelete = async () => {
    if (!sessionToDelete) return

    try {
      await agentApi.deleteSession(sessionToDelete)
      setSessions(prev => prev.filter(s => s.id !== sessionToDelete))
      if (currentSession?.id === sessionToDelete) {
        setCurrentSession(null)
        setView('list')
      }
    } catch (err) {
      // If session not found (404), just remove it from the UI
      if (err && typeof err === 'object' && 'response' in err && err.response && typeof err.response === 'object' && 'status' in err.response && err.response.status === 404) {
        setSessions(prev => prev.filter(s => s.id !== sessionToDelete))
        if (currentSession?.id === sessionToDelete) {
          setCurrentSession(null)
          setView('list')
        }
        setError('Сессия уже удалена')
      } else {
        setError('Ошибка при удалении сессии')
        console.error(err)
      }
    } finally {
      setDeleteModalOpen(false)
      setSessionToDelete(null)
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const hours = Math.floor(diff / (1000 * 60 * 60))

    if (hours < 1) {
      return 'Только что'
    } else if (hours < 24) {
      return `${hours}ч назад`
    } else {
      const days = Math.floor(hours / 24)
      return `${days}д назад`
    }
  }

  if (view === 'chat') {
    return (
      <Stack gap="md">
        <Group justify="space-between">
          <Button
            variant="light"
            onClick={() => setView('list')}
            leftSection={<span>←</span>}
          >
            Назад к сессиям
          </Button>
          {currentSession && (
            <Button
              variant="light"
              color="red"
              onClick={() => confirmDelete(currentSession.id)}
              leftSection={<span>🗑️</span>}
            >
              Удалить сессию
            </Button>
          )}
        </Group>
        <AgentChat
          session={currentSession || undefined}
          onSessionCreate={handleSessionCreate}
        />
      </Stack>
    )
  }

  if (view === 'new') {
    return (
      <Stack gap="md">
        <Button
          variant="light"
          onClick={() => setView('list')}
          leftSection={<span>←</span>}
        >
          Назад к сессиям
        </Button>
        <AgentChat
          onSessionCreate={handleSessionCreate}
        />
      </Stack>
    )
  }

  return (
    <Stack gap="md">
      <Paper shadow="xs" p="md" withBorder>
        <Stack gap="md" align="center">
          <Title order={2}>🤖 AI Агент</Title>
          <Text c="dimmed" size="sm">Управляйте чатами через умного помощника</Text>
          <Button
            onClick={() => setView('new')}
            leftSection={<span>➕</span>}
            size="lg"
          >
            Новая сессия
          </Button>
        </Stack>
      </Paper>

      {error && (
        <Alert
          color="red"
          title="⚠️ Ошибка"
          withCloseButton
          onClose={() => setError(null)}
        >
          <Group justify="space-between">
            <Text size="sm">{error}</Text>
            <Button onClick={loadSessions} variant="light" size="xs">
              Повторить
            </Button>
          </Group>
        </Alert>
      )}

      {isLoading ? (
        <Stack align="center" justify="center" p="xl">
          <Loader size="xl" />
          <Text>Загрузка сессий...</Text>
        </Stack>
      ) : sessions.length === 0 ? (
        <Paper shadow="xs" p="xl" withBorder>
          <Stack align="center" gap="md">
            <Text size="4rem">🤖</Text>
            <Title order={3}>Нет активных сессий</Title>
            <Text c="dimmed" ta="center">
              Создайте новую сессию, чтобы начать общение с AI агентом
            </Text>
            <Button
              onClick={() => setView('new')}
              leftSection={<span>➕</span>}
              size="lg"
            >
              Создать первую сессию
            </Button>
          </Stack>
        </Paper>
      ) : (
        <Stack gap="md">
          {sessions.map(session => (
            <Paper
              key={session.id}
              p="md"
              shadow="xs"
              withBorder
              style={{
                cursor: 'pointer',
                transition: 'transform 0.2s, box-shadow 0.2s'
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)'
                e.currentTarget.style.boxShadow = 'var(--mantine-shadow-md)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = 'var(--mantine-shadow-xs)'
              }}
            >
              <Group justify="space-between" wrap="nowrap">
                <Box
                  style={{ flex: 1 }}
                  onClick={() => handleSessionSelect(session)}
                >
                  <Group justify="space-between" mb="xs">
                    <Text fw={600} size="lg">
                      {session.title || 'Без названия'}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {formatDate(session.updated_at)}
                    </Text>
                  </Group>

                  <Group gap="md">
                    <Text size="sm" c="dimmed">
                      {session.agent_config.model_name || session.agent_config.model_id}
                    </Text>
                    <Badge size="sm" variant="light">
                      {session.agent_config.provider}
                    </Badge>
                    <Text size="sm" c="dimmed">
                      {session.message_count} сообщений
                    </Text>
                  </Group>
                </Box>

                <ActionIcon
                  variant="subtle"
                  color="red"
                  size="lg"
                  onClick={(e) => {
                    e.stopPropagation()
                    confirmDelete(session.id)
                  }}
                  title="Удалить сессию"
                >
                  🗑️
                </ActionIcon>
              </Group>
            </Paper>
          ))}
        </Stack>
      )}

      <Modal
        opened={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false)
          setSessionToDelete(null)
        }}
        title={<Text fw={600}>🗑️ Удаление сессии</Text>}
        centered
      >
        <Stack gap="md">
          <Text>
            Удалить эту сессию? Все сообщения будут потеряны.
          </Text>
          <Group gap="md">
            <Button
              onClick={handleSessionDelete}
              color="red"
              leftSection={<span>✅</span>}
              style={{ flex: 1 }}
            >
              Да, удалить
            </Button>
            <Button
              onClick={() => {
                setDeleteModalOpen(false)
                setSessionToDelete(null)
              }}
              variant="light"
              color="gray"
              leftSection={<span>❌</span>}
            >
              Отмена
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
