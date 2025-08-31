import React, { useState, useEffect } from 'react'
import { AgentChat } from './AgentChat'
import { agentApi } from '../services/agentApi'
import type { AgentSession } from '../types'

export const AgentManager: React.FC = () => {
  const [sessions, setSessions] = useState<AgentSession[]>([])
  const [currentSession, setCurrentSession] = useState<AgentSession | null>(null)
  const [view, setView] = useState<'list' | 'chat' | 'new'>('list')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadSessions()
  }, [])

  const loadSessions = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await agentApi.getUserSessions(20)
      setSessions(response.sessions)
    } catch (err) {
      if (err && typeof err === 'object' && 'response' in err && err.response && typeof err.response === 'object' && 'status' in err.response && err.response.status >= 500) {
        setError('Ошибка сервера при загрузке сессий')
      } else {
        setError('Ошибка при загрузке сессий')
      }
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSessionCreate = (session: AgentSession) => {
    setSessions(prev => [session, ...prev])
    setCurrentSession(session)
    setView('chat')
  }

  const handleSessionSelect = (session: AgentSession) => {
    setCurrentSession(session)
    setView('chat')
  }

  const handleSessionDelete = async (sessionId: string) => {
    if (!confirm('Удалить эту сессию? Все сообщения будут потеряны.')) {
      return
    }

    try {
      await agentApi.deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.id !== sessionId))
      if (currentSession?.id === sessionId) {
        setCurrentSession(null)
        setView('list')
      }
    } catch (err) {
      // If session not found (404), just remove it from the UI
      if (err && typeof err === 'object' && 'response' in err && err.response && typeof err.response === 'object' && 'status' in err.response && err.response.status === 404) {
        setSessions(prev => prev.filter(s => s.id !== sessionId))
        if (currentSession?.id === sessionId) {
          setCurrentSession(null)
          setView('list')
        }
        setError('Сессия уже удалена')
      } else {
        setError('Ошибка при удалении сессии')
        console.error(err)
      }
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const hours = Math.floor(diff / (1000 * 60 * 60))

    if (hours < 1) {
      return 'Только что'
    } else if (hours < 24) {
      return `${hours}ч назад`
    } else {
      const days = Math.floor(hours / 24)
      return `${days}д назад`
    }
  }

  if (view === 'chat') {
    return (
      <div className="agent-manager">
        <div className="chat-nav">
          <button onClick={() => setView('list')} className="back-button">
            ← Назад к сессиям
          </button>
          {currentSession && (
            <button
              onClick={() => handleSessionDelete(currentSession.id)}
              className="delete-button"
            >
              🗑️ Удалить сессию
            </button>
          )}
        </div>
        <AgentChat
          session={currentSession || undefined}
          onSessionCreate={handleSessionCreate}
        />
      </div>
    )
  }

  if (view === 'new') {
    return (
      <div className="agent-manager">
        <div className="chat-nav">
          <button onClick={() => setView('list')} className="back-button">
            ← Назад к сессиям
          </button>
        </div>
        <AgentChat
          onSessionCreate={handleSessionCreate}
        />
      </div>
    )
  }

  return (
    <div className="agent-manager">
      <div className="sessions-header">
        <h2>🤖 AI Агент</h2>
        <p>Управляйте чатами через умного помощника</p>

        <button
          onClick={() => setView('new')}
          className="new-session-button"
        >
          ➕ Новая сессия
        </button>
      </div>

      {error && (
        <div className="error-message">
          ⚠️ {error}
          <button onClick={loadSessions} className="retry-button">
            Повторить
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Загрузка сессий...</p>
        </div>
      ) : sessions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🤖</div>
          <h3>Нет активных сессий</h3>
          <p>Создайте новую сессию, чтобы начать общение с AI агентом</p>
          <button
            onClick={() => setView('new')}
            className="create-first-button"
          >
            Создать первую сессию
          </button>
        </div>
      ) : (
        <div className="sessions-list">
          {sessions.map(session => (
            <div key={session.id} className="session-card">
              <div
                className="session-info"
                onClick={() => handleSessionSelect(session)}
              >
                <div className="session-header">
                  <h4>{session.title || 'Без названия'}</h4>
                  <span className="session-time">
                    {formatDate(session.updated_at)}
                  </span>
                </div>

                <div className="session-details">
                  <span className="model-info">
                    {session.agent_config.model_name || session.agent_config.model_id}
                  </span>
                  <span className="provider-badge">
                    {session.agent_config.provider}
                  </span>
                  <span className="message-count">
                    {session.message_count} сообщений
                  </span>
                </div>
              </div>

              <button
                onClick={(e) => {
                  e.stopPropagation()
                  handleSessionDelete(session.id)
                }}
                className="delete-session-button"
                title="Удалить сессию"
              >
                🗑️
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Стили для менеджера сессий
const managerStyles = `
.agent-manager {
  padding: 1rem;
  height: 100%;
}

.chat-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--tg-theme-section-separator-color, #e0e0e0);
}

.back-button, .delete-button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--tg-theme-hint-color, #ccc);
  border-radius: 8px;
  background: var(--tg-theme-bg-color, white);
  color: var(--tg-theme-text-color, black);
  cursor: pointer;
  font-size: 0.9rem;
}

.delete-button {
  background: #fee;
  border-color: #fcc;
  color: #c33;
}

.sessions-header {
  text-align: center;
  margin-bottom: 2rem;
}

.sessions-header h2 {
  margin-bottom: 0.5rem;
  color: var(--tg-theme-text-color, black);
}

.sessions-header p {
  color: var(--tg-theme-hint-color, #666);
  margin-bottom: 1.5rem;
}

.new-session-button, .create-first-button {
  padding: 1rem 2rem;
  border: none;
  border-radius: 12px;
  background: var(--tg-theme-button-color, #0088cc);
  color: var(--tg-theme-button-text-color, white);
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
}

.loading-container {
  text-align: center;
  padding: 3rem;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--tg-theme-hint-color, #ddd);
  border-top: 3px solid var(--tg-theme-button-color, #0088cc);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 1rem;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.empty-state {
  text-align: center;
  padding: 3rem 2rem;
  color: var(--tg-theme-hint-color, #666);
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.empty-state h3 {
  margin-bottom: 0.5rem;
  color: var(--tg-theme-text-color, black);
}

.sessions-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.session-card {
  display: flex;
  align-items: center;
  background: var(--tg-theme-secondary-bg-color, #f8f9fa);
  border-radius: 12px;
  overflow: hidden;
  transition: transform 0.2s, box-shadow 0.2s;
}

.session-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.session-info {
  flex: 1;
  padding: 1.5rem;
  cursor: pointer;
}

.session-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.session-header h4 {
  margin: 0;
  color: var(--tg-theme-text-color, black);
  font-size: 1.1rem;
}

.session-time {
  font-size: 0.8rem;
  color: var(--tg-theme-hint-color, #666);
}

.session-details {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: var(--tg-theme-hint-color, #666);
}

.provider-badge {
  background: var(--tg-theme-button-color, #0088cc);
  color: var(--tg-theme-button-text-color, white);
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  font-size: 0.7rem;
  text-transform: uppercase;
}

.delete-session-button {
  padding: 1rem;
  border: none;
  background: transparent;
  color: var(--tg-theme-hint-color, #999);
  cursor: pointer;
  font-size: 1.2rem;
  transition: color 0.2s;
}

.delete-session-button:hover {
  color: #c33;
}

.error-message {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: #fee;
  color: #c33;
  border-radius: 8px;
  margin-bottom: 1rem;
}

.retry-button {
  padding: 0.5rem 1rem;
  border: 1px solid #fcc;
  border-radius: 6px;
  background: white;
  color: #c33;
  cursor: pointer;
  font-size: 0.8rem;
}
`

// Инжектим стили для менеджера
if (typeof document !== 'undefined') {
  const styleElement = document.createElement('style')
  styleElement.textContent = managerStyles
  document.head.appendChild(styleElement)
}
