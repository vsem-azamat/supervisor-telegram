import { useEffect, useState } from 'react'
import { useLaunchParams, useRawInitData } from '@telegram-apps/sdk-react'
import { AppShell, Tabs, Container, Badge, Group, Title, Code, ActionIcon, useMantineColorScheme } from '@mantine/core'
import BulkChatManager from './components/BulkChatManager'
import { AgentManager } from './components/AgentManager'

interface UserInfo {
  id: number
  first_name: string
  last_name?: string
  username?: string
  language_code?: string
  is_premium?: boolean
}

function App() {
  const launchParams = useLaunchParams()
  const rawInitData = useRawInitData()
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null)
  const [activeTab, setActiveTab] = useState<'bulk' | 'agent' | 'analytics' | 'settings' | 'debug'>('bulk')
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()

  useEffect(() => {
    // Parse raw init data to get user info
    if (rawInitData) {
      try {
        const parsed = new URLSearchParams(rawInitData)
        const userStr = parsed.get('user')
        if (userStr) {
          const user = JSON.parse(userStr)
          setUserInfo(user)
        }
      } catch (error) {
        console.error('Failed to parse init data:', error)
      }
    }
  }, [rawInitData])

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Container size="xl" h="100%">
          <Group h="100%" justify="space-between">
            <Title order={2}>🛡️ Moderator Bot</Title>
            <Group gap="md">
              <ActionIcon
                variant="light"
                size="lg"
                onClick={() => toggleColorScheme()}
                title={colorScheme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на темную тему'}
              >
                {colorScheme === 'dark' ? '☀️' : '🌙'}
              </ActionIcon>
              {userInfo && (
                <Badge size="lg" variant="light">
                  👋 {userInfo.first_name}
                </Badge>
              )}
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="xl">
          <Tabs value={activeTab} onChange={(value) => setActiveTab(value as typeof activeTab)}>
            <Tabs.List>
              <Tabs.Tab value="bulk">🎯 Массовые операции</Tabs.Tab>
              <Tabs.Tab value="agent">🤖 AI Агент</Tabs.Tab>
              <Tabs.Tab value="analytics">📊 Аналитика</Tabs.Tab>
              <Tabs.Tab value="settings">⚙️ Настройки</Tabs.Tab>
              <Tabs.Tab value="debug">🔧 Debug</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="bulk" pt="md">
              <BulkChatManager />
            </Tabs.Panel>

            <Tabs.Panel value="agent" pt="md">
              <AgentManager />
            </Tabs.Panel>

            <Tabs.Panel value="analytics" pt="md">
              <div style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                <Title order={2}>📊 Аналитика</Title>
                <p>🚧 В разработке</p>
                <ul style={{ textAlign: 'left', maxWidth: 400, margin: '0 auto', listStyle: 'none' }}>
                  <li>📈 Статистика чатов</li>
                  <li>👥 Активность пользователей</li>
                  <li>⚡ Модерационные действия</li>
                  <li>📋 Отчеты и экспорт</li>
                </ul>
              </div>
            </Tabs.Panel>

            <Tabs.Panel value="settings" pt="md">
              <div style={{ textAlign: 'center', padding: '3rem 2rem' }}>
                <Title order={2}>⚙️ Глобальные настройки</Title>
                <p>🚧 В разработке</p>
                <ul style={{ textAlign: 'left', maxWidth: 400, margin: '0 auto', listStyle: 'none' }}>
                  <li>🤖 Настройки бота</li>
                  <li>🔔 Уведомления</li>
                  <li>🔒 Безопасность</li>
                  <li>🌐 Локализация</li>
                </ul>
              </div>
            </Tabs.Panel>

            <Tabs.Panel value="debug" pt="md">
              <div style={{ padding: '2rem' }}>
                <Title order={2} mb="md">🔧 Отладка</Title>
                <details style={{ marginBottom: '1rem' }}>
                  <summary style={{ cursor: 'pointer', padding: '0.5rem', background: '#f5f5f5', borderRadius: '4px' }}>
                    Launch Params
                  </summary>
                  <Code block mt="sm">{JSON.stringify(launchParams, null, 2)}</Code>
                </details>
                <details style={{ marginBottom: '1rem' }}>
                  <summary style={{ cursor: 'pointer', padding: '0.5rem', background: '#f5f5f5', borderRadius: '4px' }}>
                    User Info
                  </summary>
                  <Code block mt="sm">{JSON.stringify(userInfo, null, 2)}</Code>
                </details>
                <details>
                  <summary style={{ cursor: 'pointer', padding: '0.5rem', background: '#f5f5f5', borderRadius: '4px' }}>
                    Raw Init Data
                  </summary>
                  <Code block mt="sm">{rawInitData || 'No init data available'}</Code>
                </details>
              </div>
            </Tabs.Panel>
          </Tabs>
        </Container>
      </AppShell.Main>
    </AppShell>
  )
}

export default App
