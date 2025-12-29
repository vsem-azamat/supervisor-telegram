import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { retrieveLaunchParams } from '@tma.js/sdk-react'
import { MantineProvider } from '@mantine/core'
import '@mantine/core/styles.css'
import 'katex/dist/katex.min.css'  // Required for CopilotKit math rendering
import App from './App.tsx'

// Initialize Telegram WebApp launch params
retrieveLaunchParams()

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider defaultColorScheme="light">
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
