import { useEffect, useState } from 'react'
import { useRawInitData } from '@tma.js/sdk-react'
import { Box, Group, Text, ActionIcon, useMantineColorScheme, Stack, Title, Card } from '@mantine/core'

interface UserInfo {
  id: number
  first_name: string
  last_name?: string
  username?: string
}

function App() {
  const rawInitData = useRawInitData()
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null)
  const { colorScheme, toggleColorScheme } = useMantineColorScheme()

  useEffect(() => {
    if (rawInitData) {
      try {
        const parsed = new URLSearchParams(rawInitData)
        const userStr = parsed.get('user')
        if (userStr) {
          setUserInfo(JSON.parse(userStr))
        }
      } catch (error) {
        console.error('Failed to parse init data:', error)
      }
    }
  }, [rawInitData])

  return (
    <Box className="app-root">
      <Box component="header" className="app-header">
        <Group justify="space-between" h="100%" px="md">
          <Text fw={600} size="lg">Moderator Dashboard</Text>
          <Group gap="xs">
            <ActionIcon
              variant="subtle"
              size="md"
              onClick={() => toggleColorScheme()}
              aria-label={colorScheme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {colorScheme === 'dark' ? '☀️' : '🌙'}
            </ActionIcon>
            {userInfo && (
              <Text size="sm" c="dimmed">{userInfo.first_name}</Text>
            )}
          </Group>
        </Group>
      </Box>
      <Box component="main" className="app-main" p="md">
        <Stack gap="md">
          <Title order={2}>Statistics</Title>
          <Card shadow="sm" padding="lg" radius="md" withBorder>
            <Text size="sm" c="dimmed">
              Chat statistics and moderation logs will be available here soon.
            </Text>
          </Card>

          <Title order={3} size="h4" mt="lg">Pending Tasks</Title>
          <Card shadow="xs" padding="sm" radius="md" withBorder>
            <Stack gap="xs">
              <Text size="sm">• Configure chat filters</Text>
              <Text size="sm">• Review reported messages</Text>
              <Text size="sm">• Update moderation rules</Text>
            </Stack>
          </Card>
        </Stack>
      </Box>
    </Box>
  )
}

export default App
