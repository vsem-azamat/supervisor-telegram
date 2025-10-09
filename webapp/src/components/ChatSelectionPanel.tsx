import { useState, useMemo } from 'react'
import {
  Paper, Stack, Group, Text, TextInput, Button, Checkbox,
  Select, Badge, ScrollArea, Collapse, Title
} from '@mantine/core'
import type { Chat, ChatFilters } from '../types'

interface ChatSelectionPanelProps {
  chats: Chat[]
  selectedChats: number[]
  onSelectionChange: (selectedIds: number[]) => void
}

const ChatSelectionPanel: React.FC<ChatSelectionPanelProps> = ({
  chats,
  selectedChats,
  onSelectionChange
}) => {
  const [filters, setFilters] = useState<ChatFilters>({
    search: '',
    type: [],
    isActive: undefined
  })
  const [showFilters, setShowFilters] = useState(false)

  // Filter chats based on current filters
  const filteredChats = useMemo(() => {
    return chats.filter(chat => {
      // Search filter
      if (filters.search) {
        const searchLower = filters.search.toLowerCase()
        const matchesTitle = chat.title.toLowerCase().includes(searchLower)
        const matchesDescription = chat.description?.toLowerCase().includes(searchLower)
        if (!matchesTitle && !matchesDescription) return false
      }

      // Type filter
      if (filters.type.length > 0 && !filters.type.includes(chat.type)) {
        return false
      }

      // Active filter
      if (filters.isActive !== undefined && chat.is_active !== filters.isActive) {
        return false
      }

      // Member count filters
      if (filters.memberCountMin && (chat.member_count || 0) < filters.memberCountMin) {
        return false
      }
      if (filters.memberCountMax && (chat.member_count || 0) > filters.memberCountMax) {
        return false
      }

      return true
    })
  }, [chats, filters])

  const handleChatToggle = (chatId: number) => {
    const newSelection = selectedChats.includes(chatId)
      ? selectedChats.filter(id => id !== chatId)
      : [...selectedChats, chatId]
    onSelectionChange(newSelection)
  }

  const handleSelectAll = () => {
    const allFilteredIds = filteredChats.map(chat => chat.id)
    onSelectionChange(allFilteredIds)
  }

  const handleSelectNone = () => {
    onSelectionChange([])
  }

  const handleInvertSelection = () => {
    const filteredIds = filteredChats.map(chat => chat.id)
    const newSelection = filteredIds.filter(id => !selectedChats.includes(id))
    onSelectionChange([...selectedChats.filter(id => !filteredIds.includes(id)), ...newSelection])
  }

  const formatChatType = (type: string) => {
    const types = {
      'group': '👥 Группа',
      'supergroup': '🔥 Супергруппа',
      'channel': '📢 Канал'
    }
    return types[type as keyof typeof types] || type
  }

  const formatMemberCount = (count?: number) => {
    if (!count) return 'Неизвестно'
    if (count < 1000) return count.toString()
    if (count < 1000000) return `${(count / 1000).toFixed(1)}K`
    return `${(count / 1000000).toFixed(1)}M`
  }

  return (
    <Paper shadow="xs" withBorder>
      <Stack gap={0}>
        {/* Header */}
        <Group justify="space-between" p="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
          <Title order={4}>📋 Выбор чатов</Title>
          <Button
            variant="light"
            size="xs"
            onClick={() => setShowFilters(!showFilters)}
          >
            🔍 Фильтры
          </Button>
        </Group>

        {/* Filters */}
        <Collapse in={showFilters}>
          <Stack gap="md" p="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
            <TextInput
              placeholder="Поиск по названию или описанию..."
              value={filters.search}
              onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value }))}
            />

            <Group grow>
              <Select
                label="Статус"
                placeholder="Все"
                value={filters.isActive === undefined ? null : filters.isActive ? 'true' : 'false'}
                onChange={(value) => {
                  const val = value === null ? undefined : value === 'true'
                  setFilters(prev => ({ ...prev, isActive: val }))
                }}
                data={[
                  { value: 'true', label: 'Активные' },
                  { value: 'false', label: 'Неактивные' }
                ]}
                clearable
              />
            </Group>

            <div>
              <Text size="sm" fw={500} mb="xs">Тип чата:</Text>
              <Group>
                {['group', 'supergroup', 'channel'].map(type => (
                  <Checkbox
                    key={type}
                    label={formatChatType(type)}
                    checked={filters.type.includes(type)}
                    onChange={(e) => {
                      const newTypes = e.currentTarget.checked
                        ? [...filters.type, type]
                        : filters.type.filter(t => t !== type)
                      setFilters(prev => ({ ...prev, type: newTypes }))
                    }}
                  />
                ))}
              </Group>
            </div>
          </Stack>
        </Collapse>

        {/* Selection Controls */}
        <Group justify="space-between" p="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
          <Group gap="md">
            <Text size="sm" c="dimmed">
              Показано: <strong>{filteredChats.length}</strong> из {chats.length}
            </Text>
            <Text size="sm" c="dimmed">
              Выбрано: <strong>{selectedChats.length}</strong>
            </Text>
          </Group>

          <Group gap="xs">
            <Button onClick={handleSelectAll} variant="light" size="xs">
              Выбрать все
            </Button>
            <Button onClick={handleSelectNone} variant="light" size="xs" color="gray">
              Снять все
            </Button>
            <Button onClick={handleInvertSelection} variant="light" size="xs" color="gray">
              Инвертировать
            </Button>
          </Group>
        </Group>

        {/* Chat List */}
        <ScrollArea h={500}>
          {filteredChats.length === 0 ? (
            <Stack align="center" justify="center" p="xl" gap="xs">
              <Text size="xl">🔍</Text>
              <Text fw={500}>Чаты не найдены</Text>
              <Text size="sm" c="dimmed">Попробуйте изменить условия поиска</Text>
            </Stack>
          ) : (
            <Stack gap={0}>
              {filteredChats.map(chat => (
                <Paper
                  key={chat.id}
                  p="md"
                  style={{
                    cursor: 'pointer',
                    borderBottom: '1px solid var(--mantine-color-gray-2)',
                    backgroundColor: selectedChats.includes(chat.id)
                      ? 'var(--mantine-color-blue-0)'
                      : undefined
                  }}
                  onClick={() => handleChatToggle(chat.id)}
                >
                  <Group align="flex-start" wrap="nowrap">
                    <Checkbox
                      checked={selectedChats.includes(chat.id)}
                      onChange={() => {}} // Handled by parent click
                      style={{ marginTop: 2 }}
                    />

                    <Stack gap="xs" style={{ flex: 1 }}>
                      <Group justify="space-between">
                        <Text fw={600}>{chat.title}</Text>
                        <Group gap="xs">
                          <Badge size="sm" variant="light">
                            {formatChatType(chat.type)}
                          </Badge>
                          <Text size="xl">
                            {chat.is_active ? '🟢' : '🔴'}
                          </Text>
                        </Group>
                      </Group>

                      <Group gap="md">
                        <Text size="sm" c="dimmed">
                          👥 {formatMemberCount(chat.member_count)}
                        </Text>
                        <Text size="sm" c="dimmed">
                          ID: {chat.id}
                        </Text>
                      </Group>

                      {chat.description && (
                        <Text size="sm" c="dimmed" lineClamp={2}>
                          {chat.description}
                        </Text>
                      )}

                      {chat.welcome_message && (
                        <Paper p="xs" bg="blue.0" withBorder>
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            <strong>👋 Приветствие:</strong> {chat.welcome_message}
                          </Text>
                        </Paper>
                      )}
                    </Stack>
                  </Group>
                </Paper>
              ))}
            </Stack>
          )}
        </ScrollArea>
      </Stack>
    </Paper>
  )
}

export default ChatSelectionPanel
