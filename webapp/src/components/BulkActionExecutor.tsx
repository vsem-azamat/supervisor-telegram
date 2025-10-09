import { useState } from 'react'
import {
  Paper, Stack, Group, Text, Button, Modal, Alert, Badge, Box
} from '@mantine/core'
import type { Chat, BulkActionConfig, BulkExecutionResult } from '../types'

interface BulkActionExecutorProps {
  actionConfig: BulkActionConfig
  selectedChats: number[]
  chats: Chat[]
  onExecute: () => void
  onReset: () => void
  isExecuting: boolean
  executionResults: BulkExecutionResult | null
}

const BulkActionExecutor: React.FC<BulkActionExecutorProps> = ({
  actionConfig,
  selectedChats,
  chats,
  onExecute,
  onReset,
  isExecuting,
  executionResults
}) => {
  const [showConfirmation, setShowConfirmation] = useState(false)

  const selectedChatTitles = chats
    .filter(chat => selectedChats.includes(chat.id))
    .map(chat => chat.title)

  const getActionDescription = () => {
    switch (actionConfig.actionType) {
      case 'update_description':
        return `Обновить описание для ${selectedChats.length} чатов`
      case 'update_welcome':
        return `Настроить приветствие в ${selectedChats.length} чатах`
      case 'broadcast_message':
        return `Отправить сообщение в ${selectedChats.length} чатов`
      case 'chat_settings':
        return `Изменить настройки ${selectedChats.length} чатов`
      case 'user_management':
        return `Выполнить действия с пользователями в ${selectedChats.length} чатах`
      default:
        return `Выполнить действие в ${selectedChats.length} чатах`
    }
  }

  const getActionIcon = () => {
    switch (actionConfig.actionType) {
      case 'update_description': return '📝'
      case 'update_welcome': return '👋'
      case 'broadcast_message': return '📢'
      case 'chat_settings': return '⚙️'
      case 'user_management': return '👥'
      default: return '🛠️'
    }
  }

  const handleExecute = () => {
    if (actionConfig.confirmationRequired) {
      setShowConfirmation(true)
    } else {
      onExecute()
    }
  }

  const handleConfirmedExecute = () => {
    setShowConfirmation(false)
    onExecute()
  }

  const renderConfigPreview = () => {
    return (
      <Box>
        <Text size="sm" fw={600} mb="xs">Параметры действия:</Text>
        <Stack gap="xs">
          {Object.entries(actionConfig.values).map(([key, value]) => (
            <Group key={key} justify="space-between">
              <Text size="sm" c="dimmed">{key}:</Text>
              <Text size="sm" fw={500}>
                {typeof value === 'boolean'
                  ? (value ? 'Да' : 'Нет')
                  : typeof value === 'string' && value.length > 50
                    ? `${value.slice(0, 50)}...`
                    : String(value)
                }
              </Text>
            </Group>
          ))}
        </Stack>
      </Box>
    )
  }

  const renderExecutionResults = () => {
    if (!executionResults) return null

    return (
      <Paper shadow="xs" p="md" withBorder>
        <Stack gap="md">
          <Alert
            color={executionResults.success ? 'green' : 'red'}
            title={executionResults.success ? '✅ Операция завершена' : '❌ Операция не выполнена'}
          >
            {executionResults.error ? (
              <Text>{executionResults.error}</Text>
            ) : (
              <Stack gap="md">
                <Group gap="xl">
                  <div>
                    <Text size="xs" c="dimmed">Всего чатов:</Text>
                    <Text size="lg" fw={700}>{executionResults.totalChats}</Text>
                  </div>
                  <div>
                    <Text size="xs" c="dimmed">Успешно:</Text>
                    <Text size="lg" fw={700} c="green">{executionResults.successCount}</Text>
                  </div>
                  {executionResults.failureCount > 0 && (
                    <div>
                      <Text size="xs" c="dimmed">Ошибок:</Text>
                      <Text size="lg" fw={700} c="red">{executionResults.failureCount}</Text>
                    </div>
                  )}
                </Group>

                {executionResults.results && executionResults.results.length > 0 && (
                  <Box>
                    <Text size="sm" fw={600} mb="xs">Детальные результаты:</Text>
                    <Stack gap="xs">
                      {executionResults.results.map(result => (
                        <Paper
                          key={result.chatId}
                          p="xs"
                          withBorder
                          style={{
                            borderColor: result.success
                              ? 'var(--mantine-color-green-3)'
                              : 'var(--mantine-color-red-3)'
                          }}
                        >
                          <Group gap="xs" wrap="nowrap">
                            <Text size="xl">{result.success ? '✅' : '❌'}</Text>
                            <Box style={{ flex: 1 }}>
                              <Text size="sm" fw={600}>{result.chatTitle}</Text>
                              {result.error && (
                                <Text size="xs" c="red">{result.error}</Text>
                              )}
                              {result.changes && (
                                <Text size="xs" c="dimmed">
                                  Изменения: {Object.keys(result.changes).join(', ')}
                                </Text>
                              )}
                            </Box>
                          </Group>
                        </Paper>
                      ))}
                    </Stack>
                  </Box>
                )}
              </Stack>
            )}
          </Alert>

          <Button onClick={onReset} variant="light" leftSection={<span>🔄</span>}>
            Начать заново
          </Button>
        </Stack>
      </Paper>
    )
  }

  if (executionResults) {
    return renderExecutionResults()
  }

  return (
    <Paper shadow="xs" p="md" withBorder>
      <Stack gap="md">
        <Group>
          <Text size="xl">{getActionIcon()}</Text>
          <Text fw={600} size="lg">Выполнение действия</Text>
        </Group>

        <Paper p="md" withBorder>
          <Stack gap="md">
            <Text fw={600}>{getActionDescription()}</Text>

            <Box>
              <Text size="sm" fw={600} mb="xs">Выбранные чаты:</Text>
              <Group gap="xs">
                {selectedChatTitles.slice(0, 3).map(title => (
                  <Badge key={title} variant="light">
                    {title}
                  </Badge>
                ))}
                {selectedChatTitles.length > 3 && (
                  <Badge variant="outline">
                    +{selectedChatTitles.length - 3} еще
                  </Badge>
                )}
              </Group>
            </Box>

            {renderConfigPreview()}
          </Stack>
        </Paper>

        <Group gap="md">
          <Button
            onClick={handleExecute}
            disabled={isExecuting}
            loading={isExecuting}
            leftSection={isExecuting ? undefined : <span>▶️</span>}
            style={{ flex: 1 }}
          >
            {isExecuting ? 'Выполняется...' : 'Выполнить действие'}
          </Button>

          <Button
            onClick={onReset}
            disabled={isExecuting}
            variant="light"
            color="gray"
            leftSection={<span>🔄</span>}
          >
            Сбросить
          </Button>
        </Group>
      </Stack>

      <Modal
        opened={showConfirmation}
        onClose={() => setShowConfirmation(false)}
        title={<Text fw={600}>⚠️ Подтверждение действия</Text>}
        centered
      >
        <Stack gap="md">
          <Text>
            Вы уверены, что хотите выполнить это действие для {selectedChats.length} чатов?
          </Text>

          <Alert color="yellow" icon={<span>⚠️</span>}>
            <Text size="sm" fw={600}>Внимание:</Text>
            <Text size="sm">Это действие может быть необратимым.</Text>
          </Alert>

          {renderConfigPreview()}

          <Group gap="md">
            <Button
              onClick={handleConfirmedExecute}
              color="green"
              leftSection={<span>✅</span>}
              style={{ flex: 1 }}
            >
              Да, выполнить
            </Button>
            <Button
              onClick={() => setShowConfirmation(false)}
              variant="light"
              color="red"
              leftSection={<span>❌</span>}
            >
              Отмена
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  )
}

export default BulkActionExecutor
