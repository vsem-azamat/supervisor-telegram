import React, { useState, useEffect, useRef, useCallback } from 'react'
import { agentApi } from '../services/agentApi'
import type {
  AgentSession,
  AgentMessage,
  AgentModel,
  ModelProvider,
  CreateSessionRequest
} from '../types'

interface AgentChatProps {
  session?: AgentSession
  onSessionCreate?: (session: AgentSession) => void
}

export const AgentChat: React.FC<AgentChatProps> = ({
  session: initialSession,
  onSessionCreate
}) => {
  const [session, setSession] = useState<AgentSession | null>(initialSession || null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [newMessage, setNewMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showModelSelector, setShowModelSelector] = useState(false)
  const [availableModels, setAvailableModels] = useState<{
    openai: AgentModel[]
    openrouter: AgentModel[]
  }>({ openai: [], openrouter: [] })
  const [selectedProvider, setSelectedProvider] = useState<ModelProvider>('openai')
  const [selectedModel, setSelectedModel] = useState<AgentModel | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const loadAvailableModels = useCallback(async () => {
    try {
      const [openaiModels, openrouterModels] = await Promise.all([
        agentApi.getAvailableModels('openai'),
        agentApi.getAvailableModels('openrouter')
      ])
      setAvailableModels({
        openai: openaiModels,
        openrouter: openrouterModels
      })
      if (openaiModels.length > 0) {
        setSelectedModel(openaiModels[0])
      }
    } catch (err) {
      setError('Ошибка при загрузке моделей')
      console.error(err)
    }
  }, [])

  const loadMessages = useCallback(async () => {
    if (!session) return

    try {
      const msgs = await agentApi.getSessionMessages(session.id)
      setMessages(msgs)
    } catch (err) {
      setError('Ошибка при загрузке сообщений')
      console.error(err)
    }
  }, [session])

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (session) {
      loadMessages()
    }
  }, [session, loadMessages])

  useEffect(() => {
    if (!session) {
      setShowModelSelector(true)
      loadAvailableModels()
    }
  }, [session, loadAvailableModels])

  const createSession = async () => {
    if (!selectedModel) {
      setError('Выберите модель')
      return
    }

    try {
      const createRequest: CreateSessionRequest = {
        agent_config: {
          provider: selectedModel.provider,
          model_id: selectedModel.model_id,
          model_name: selectedModel.model_name,
          temperature: selectedModel.temperature,
          max_tokens: selectedModel.max_tokens
        },
        title: `Чат с ${selectedModel.model_name}`
      }

      const newSession = await agentApi.createSession(createRequest)
      setSession(newSession)
      setShowModelSelector(false)
      onSessionCreate?.(newSession)
    } catch (err) {
      setError('Ошибка при создании сессии')
      console.error(err)
    }
  }

  const sendMessage = async () => {
    if (!newMessage.trim() || !session || isLoading) return

    const userMessage: AgentMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: newMessage,
      timestamp: new Date().toISOString()
    }

    setMessages(prev => [...prev, userMessage])
    setNewMessage('')
    setIsLoading(true)
    setError(null)

    try {
      const response = await agentApi.sendMessage(session.id, { message: newMessage })

      const assistantMessage: AgentMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.message,
        timestamp: response.timestamp
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (err) {
      setError('Ошибка при отправке сообщения')
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  if (showModelSelector) {
    return (
      <div className="agent-chat-setup">
        <div className="setup-container">
          <h2>🤖 Создать сессию с AI агентом</h2>

          <div className="provider-selector">
            <label>Провайдер:</label>
            <select
              value={selectedProvider}
              onChange={(e) => {
                const provider = e.target.value as ModelProvider
                setSelectedProvider(provider)
                if (availableModels[provider].length > 0) {
                  setSelectedModel(availableModels[provider][0])
                }
              }}
            >
              <option value="openai">OpenAI</option>
              <option value="openrouter">OpenRouter</option>
            </select>
          </div>

          <div className="model-selector">
            <label>Модель:</label>
            <select
              value={selectedModel?.model_id || ''}
              onChange={(e) => {
                const model = availableModels[selectedProvider].find(m => m.model_id === e.target.value)
                setSelectedModel(model || null)
              }}
            >
              {availableModels[selectedProvider].map(model => (
                <option key={model.model_id} value={model.model_id}>
                  {model.model_name} {model.max_tokens ? `(${model.max_tokens} tokens)` : ''}
                </option>
              ))}
            </select>
          </div>

          {selectedModel && (
            <div className="model-description">
              <p>{selectedModel.description}</p>
            </div>
          )}

          <button onClick={createSession} disabled={!selectedModel}>
            Создать сессию
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="agent-chat">
      <div className="chat-header">
        <h3>🤖 {session?.title || 'AI Агент'}</h3>
        {session && (
          <div className="session-info">
            <span className="model-info">
              {session.agent_config.model_name} ({session.agent_config.provider})
            </span>
            <span className="message-count">{messages.length} сообщений</span>
          </div>
        )}
      </div>

      <div className="messages-container">
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.role}`}>
            <div className="message-header">
              <span className="role">
                {message.role === 'user' ? '👤' : '🤖'}
              </span>
              <span className="timestamp">
                {new Date(message.timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div className="message-content">
              {message.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message assistant">
            <div className="message-header">
              <span className="role">🤖</span>
              <span className="loading">Печатает...</span>
            </div>
            <div className="message-content">
              <div className="loading-dots">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {error && (
        <div className="error-message">
          ⚠️ {error}
        </div>
      )}

      <div className="message-input">
        <textarea
          value={newMessage}
          onChange={(e) => setNewMessage(e.target.value)}
          onKeyDown={handleKeyPress}
          placeholder="Напишите сообщение агенту..."
          rows={3}
          disabled={isLoading}
        />
        <button
          onClick={sendMessage}
          disabled={!newMessage.trim() || isLoading}
        >
          {isLoading ? '⏳' : '📤'}
        </button>
      </div>
    </div>
  )
}

// Добавим базовые стили
const styles = `
.agent-chat, .agent-chat-setup {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 600px;
}

.setup-container {
  padding: 2rem;
  text-align: center;
  background: var(--tg-theme-secondary-bg-color, #f8f9fa);
  border-radius: 12px;
  margin: 1rem;
}

.provider-selector, .model-selector {
  margin: 1rem 0;
  text-align: left;
}

.provider-selector label, .model-selector label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 600;
}

.provider-selector select, .model-selector select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid var(--tg-theme-hint-color, #ccc);
  border-radius: 8px;
  background: var(--tg-theme-bg-color, white);
  color: var(--tg-theme-text-color, black);
}

.model-description {
  margin: 1rem 0;
  padding: 1rem;
  background: var(--tg-theme-bg-color, white);
  border-radius: 8px;
  font-size: 0.9rem;
  color: var(--tg-theme-hint-color, #666);
}

.chat-header {
  padding: 1rem;
  border-bottom: 1px solid var(--tg-theme-section-separator-color, #e0e0e0);
  background: var(--tg-theme-secondary-bg-color, #f8f9fa);
}

.session-info {
  display: flex;
  gap: 1rem;
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: var(--tg-theme-hint-color, #666);
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  background: var(--tg-theme-bg-color, white);
}

.message {
  margin-bottom: 1rem;
  padding: 1rem;
  border-radius: 12px;
}

.message.user {
  background: var(--tg-theme-button-color, #0088cc);
  color: var(--tg-theme-button-text-color, white);
  margin-left: 2rem;
}

.message.assistant {
  background: var(--tg-theme-secondary-bg-color, #f8f9fa);
  color: var(--tg-theme-text-color, black);
  margin-right: 2rem;
}

.message-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
  font-size: 0.8rem;
}

.message-content {
  line-height: 1.4;
  white-space: pre-wrap;
}

.loading-dots {
  display: flex;
  gap: 0.3rem;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tg-theme-hint-color, #999);
  animation: pulse 1.5s infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.5s; }
.loading-dots span:nth-child(3) { animation-delay: 1s; }

@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.message-input {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  border-top: 1px solid var(--tg-theme-section-separator-color, #e0e0e0);
  background: var(--tg-theme-secondary-bg-color, #f8f9fa);
}

.message-input textarea {
  flex: 1;
  padding: 0.75rem;
  border: 1px solid var(--tg-theme-hint-color, #ccc);
  border-radius: 8px;
  background: var(--tg-theme-bg-color, white);
  color: var(--tg-theme-text-color, black);
  resize: none;
}

.message-input button {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  background: var(--tg-theme-button-color, #0088cc);
  color: var(--tg-theme-button-text-color, white);
  cursor: pointer;
  font-size: 1.2rem;
}

.message-input button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-message {
  padding: 1rem;
  background: #fee;
  color: #c33;
  border-radius: 8px;
  margin: 1rem;
  text-align: center;
}

.setup-container button {
  padding: 1rem 2rem;
  border: none;
  border-radius: 8px;
  background: var(--tg-theme-button-color, #0088cc);
  color: var(--tg-theme-button-text-color, white);
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  margin-top: 1rem;
}

.setup-container button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
`

// Инжектим стили
if (typeof document !== 'undefined') {
  const styleElement = document.createElement('style')
  styleElement.textContent = styles
  document.head.appendChild(styleElement)
}
