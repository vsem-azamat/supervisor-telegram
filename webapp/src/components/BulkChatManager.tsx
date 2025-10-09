import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Stack, Paper, Text, Group, Badge, Grid, Loader, Alert, Button, Title } from '@mantine/core'
import ChatSelectionPanel from './ChatSelectionPanel'
import ActionConfigPanel from './ActionConfigPanel'
import BulkActionExecutor from './BulkActionExecutor'
import { apiService } from '../services/api'
import type { BulkActionConfig, BulkExecutionResult } from '../types'

const BulkChatManager: React.FC = () => {
  const [selectedChats, setSelectedChats] = useState<number[]>([])
  const [actionConfig, setActionConfig] = useState<BulkActionConfig | null>(null)
  const [isExecuting, setIsExecuting] = useState(false)
  const [executionResults, setExecutionResults] = useState<BulkExecutionResult | null>(null)

  // Fetch chats data
  const { data: chats = [], isLoading, error } = useQuery({
    queryKey: ['chats'],
    queryFn: () => apiService.getChats(),
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  })

  const handleChatSelection = (chatIds: number[]) => {
    setSelectedChats(chatIds)
  }

  const handleActionConfig = (config: BulkActionConfig | null) => {
    setActionConfig(config)
  }

  const handleExecuteAction = async () => {
    if (!actionConfig || selectedChats.length === 0) return

    setIsExecuting(true)
    setExecutionResults(null)

    try {
      const results = await apiService.bulkUpdateChats(selectedChats, actionConfig)
      setExecutionResults(results)
    } catch (error) {
      console.error('Bulk action failed:', error)
      setExecutionResults({
        success: false,
        totalChats: selectedChats.length,
        successCount: 0,
        failureCount: selectedChats.length,
        results: [],
        error: 'Операция не выполнена'
      })
    } finally {
      setIsExecuting(false)
    }
  }

  const handleReset = () => {
    setSelectedChats([])
    setActionConfig(null)
    setExecutionResults(null)
  }

  if (isLoading) {
    return (
      <Stack align="center" justify="center" h={400}>
        <Loader size="xl" />
        <Text>Загрузка чатов...</Text>
      </Stack>
    )
  }

  if (error) {
    return (
      <Alert color="red" title="❌ Ошибка загрузки" icon={<span>❌</span>}>
        <Text>Не удалось загрузить список чатов</Text>
        <Text size="sm" c="dimmed" mt="xs">
          {error instanceof Error ? error.message : 'Неизвестная ошибка'}
        </Text>
        <Button
          onClick={() => window.location.reload()}
          mt="md"
          variant="light"
          leftSection={<span>🔄</span>}
        >
          Перезагрузить
        </Button>
      </Alert>
    )
  }

  return (
    <Stack gap="md">
      <Paper shadow="xs" p="md" withBorder>
        <Group justify="space-between">
          <Title order={3}>🎯 Массовые операции с чатами</Title>
          <Group gap="lg">
            <Group gap="xs">
              <Text size="sm" c="dimmed">📊 Всего чатов:</Text>
              <Badge size="lg" variant="light">{chats.length}</Badge>
            </Group>
            <Group gap="xs">
              <Text size="sm" c="dimmed">✅ Выбрано:</Text>
              <Badge size="lg" color="blue">{selectedChats.length}</Badge>
            </Group>
          </Group>
        </Group>
      </Paper>

      <Grid>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack gap="md">
            <ActionConfigPanel
              onConfigChange={handleActionConfig}
              selectedCount={selectedChats.length}
            />

            {actionConfig && selectedChats.length > 0 && (
              <BulkActionExecutor
                actionConfig={actionConfig}
                selectedChats={selectedChats}
                chats={chats}
                onExecute={handleExecuteAction}
                onReset={handleReset}
                isExecuting={isExecuting}
                executionResults={executionResults}
              />
            )}
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 7 }}>
          <ChatSelectionPanel
            chats={chats}
            selectedChats={selectedChats}
            onSelectionChange={handleChatSelection}
          />
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

export default BulkChatManager
