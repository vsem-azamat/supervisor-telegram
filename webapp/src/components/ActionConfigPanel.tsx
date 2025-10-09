import { useState, useEffect } from 'react'
import {
  Paper, Stack, Group, Title, Badge, Button, Textarea,
  TextInput, NumberInput, Checkbox, Select, Radio, Text, SimpleGrid
} from '@mantine/core'
import type { BulkActionType, BulkActionConfig, ActionField } from '../types'

interface ActionConfigPanelProps {
  onConfigChange: (config: BulkActionConfig | null) => void
  selectedCount: number
}

const BULK_ACTIONS: BulkActionType[] = [
  {
    id: 'update_description',
    name: 'Изменить описание',
    icon: '📝',
    description: 'Массовое обновление описания чатов',
    category: 'content',
    fields: [
      {
        key: 'description',
        label: 'Новое описание',
        type: 'textarea',
        required: true,
        placeholder: 'Введите новое описание для выбранных чатов...',
        validation: { maxLength: 500 }
      }
    ]
  },
  {
    id: 'update_welcome',
    name: 'Настроить приветствие',
    icon: '👋',
    description: 'Изменить приветственное сообщение',
    category: 'content',
    fields: [
      {
        key: 'welcome_message',
        label: 'Текст приветствия',
        type: 'textarea',
        required: true,
        placeholder: 'Добро пожаловать в наш чат! 🎓',
        validation: { maxLength: 1000 }
      },
      {
        key: 'auto_delete_delay',
        label: 'Автоудаление через (сек)',
        type: 'number',
        placeholder: '300',
        validation: { min: 10, max: 3600 }
      }
    ]
  },
  {
    id: 'chat_settings',
    name: 'Настройки чата',
    icon: '⚙️',
    description: 'Изменить основные настройки чатов',
    category: 'settings',
    fields: [
      {
        key: 'is_active',
        label: 'Активировать чат',
        type: 'boolean'
      },
      {
        key: 'moderation_level',
        label: 'Уровень модерации',
        type: 'select',
        options: [
          { value: 'low', label: 'Низкий' },
          { value: 'medium', label: 'Средний' },
          { value: 'high', label: 'Высокий' }
        ]
      }
    ]
  }
]

const ActionConfigPanel: React.FC<ActionConfigPanelProps> = ({
  onConfigChange,
  selectedCount
}) => {
  const [selectedAction, setSelectedAction] = useState<BulkActionType | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [applyTo, setApplyTo] = useState<'selected' | 'all'>('selected')

  useEffect(() => {
    if (selectedAction) {
      const config: BulkActionConfig = {
        actionType: selectedAction.id,
        values,
        applyTo,
        confirmationRequired: selectedAction.category === 'moderation'
      }
      onConfigChange(config)
    } else {
      onConfigChange(null)
    }
  }, [selectedAction, values, applyTo, onConfigChange])

  const handleActionSelect = (action: BulkActionType) => {
    setSelectedAction(action)
    setValues({})
  }

  const handleValueChange = (key: string, value: unknown) => {
    setValues(prev => ({ ...prev, [key]: value }))
  }

  const renderField = (field: ActionField) => {
    const value = values[field.key] || ''

    switch (field.type) {
      case 'text':
        return (
          <TextInput
            value={value as string}
            onChange={(e) => handleValueChange(field.key, e.target.value)}
            placeholder={field.placeholder}
          />
        )

      case 'textarea':
        return (
          <Textarea
            value={value as string}
            onChange={(e) => handleValueChange(field.key, e.target.value)}
            placeholder={field.placeholder}
            rows={4}
            maxLength={field.validation?.maxLength}
          />
        )

      case 'number':
        return (
          <NumberInput
            value={value as number | ''}
            onChange={(val) => handleValueChange(field.key, val)}
            placeholder={field.placeholder}
            min={field.validation?.min}
            max={field.validation?.max}
          />
        )

      case 'boolean':
        return (
          <Checkbox
            checked={Boolean(value)}
            onChange={(e) => handleValueChange(field.key, e.currentTarget.checked)}
            label={field.label}
          />
        )

      case 'select':
        return (
          <Select
            value={value as string}
            onChange={(val) => handleValueChange(field.key, val)}
            placeholder="Выберите вариант"
            data={field.options?.map(opt => ({ value: opt.value, label: opt.label })) || []}
          />
        )

      default:
        return null
    }
  }

  const groupedActions = BULK_ACTIONS.reduce((acc, action) => {
    if (!acc[action.category]) acc[action.category] = []
    acc[action.category].push(action)
    return acc
  }, {} as Record<string, BulkActionType[]>)

  const categoryNames = {
    content: 'Контент',
    settings: 'Настройки',
    moderation: 'Модерация',
    communication: 'Коммуникации'
  }

  return (
    <Paper shadow="xs" withBorder>
      <Group justify="space-between" p="md" style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}>
        <Title order={4}>🛠️ Настройка действий</Title>
        {selectedCount > 0 ? (
          <Badge size="lg" color="blue">{selectedCount} выбрано</Badge>
        ) : (
          <Badge size="lg" variant="light" color="gray">Выберите чаты</Badge>
        )}
      </Group>

      {!selectedAction ? (
        <Stack gap="lg" p="md">
          {Object.entries(groupedActions).map(([category, actions]) => (
            <div key={category}>
              <Text size="sm" fw={600} c="blue" mb="xs">
                {categoryNames[category as keyof typeof categoryNames]}
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                {actions.map(action => (
                  <Button
                    key={action.id}
                    onClick={() => handleActionSelect(action)}
                    disabled={selectedCount === 0}
                    variant="light"
                    h="auto"
                    p="md"
                    styles={{
                      root: {
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem'
                      }
                    }}
                  >
                    <Text size="2rem">{action.icon}</Text>
                    <Text size="sm" fw={600}>{action.name}</Text>
                  </Button>
                ))}
              </SimpleGrid>
            </div>
          ))}
        </Stack>
      ) : (
        <Stack gap="md" p="md">
          <Group>
            <Button
              variant="subtle"
              size="xs"
              onClick={() => setSelectedAction(null)}
            >
              ← Назад
            </Button>
            <Group gap="xs">
              <Text size="xl">{selectedAction.icon}</Text>
              <Text fw={600}>{selectedAction.name}</Text>
            </Group>
          </Group>

          <Stack gap="md">
            {selectedAction.fields.map(field => (
              <div key={field.key}>
                {field.type !== 'boolean' && (
                  <Text size="sm" fw={500} mb={5}>
                    {field.label}
                    {field.required && <span style={{ color: 'red' }}> *</span>}
                  </Text>
                )}
                {renderField(field)}
              </div>
            ))}

            <Radio.Group
              value={applyTo}
              onChange={(val) => setApplyTo(val as 'selected')}
            >
              <Radio
                value="selected"
                label={`Применить к выбранным (${selectedCount}) чатам`}
              />
            </Radio.Group>
          </Stack>
        </Stack>
      )}
    </Paper>
  )
}

export default ActionConfigPanel
