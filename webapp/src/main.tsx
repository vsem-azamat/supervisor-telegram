import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { retrieveLaunchParams } from '@telegram-apps/sdk-react'
import './index.css'
import App from './App.tsx'

// Initialize Telegram WebApp launch params
retrieveLaunchParams()

const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
