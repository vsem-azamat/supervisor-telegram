import axios from 'axios'
import { retrieveLaunchParams } from '@tma.js/sdk'

// Telegram WebApp type declaration
declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string
        initDataUnsafe: Record<string, unknown>
      }
    }
  }
}

/**
 * Shared axios instance with Telegram WebApp authentication
 */
export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Add Telegram initData to all requests for authentication
 */
apiClient.interceptors.request.use(
  (config) => {
    try {
      // Get raw initData from Telegram.WebApp (primary method)
      let initDataRaw = window.Telegram?.WebApp?.initData

      // Fallback: Try SDK's retrieveLaunchParams
      if (!initDataRaw) {
        const launchParams = retrieveLaunchParams()
        initDataRaw = launchParams?.initDataRaw as string | undefined
      }

      if (initDataRaw) {
        config.headers['X-Telegram-Init-Data'] = initDataRaw
      } else {
        console.warn('No Telegram initData available. Make sure to open this app from Telegram bot.')
      }
    } catch (error) {
      console.error('Failed to add Telegram authentication:', error)
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/**
 * Handle authentication errors
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.error('Authentication failed:', error.response.data)
      // You could add logic here to show error to user
    } else if (error.response?.status === 403) {
      console.error('Access denied:', error.response.data)
      // You could redirect to error page or show message
    }
    return Promise.reject(error)
  }
)

export default apiClient
