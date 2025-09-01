import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Chat } from '../types';
import { chatAPI } from '../services/api';

interface ChatCardProps {
  chat: Chat;
  isSelected: boolean;
  onSelect?: (selected: boolean) => void;
  onClick?: () => void;
}

const ChatCard: React.FC<ChatCardProps> = ({
  chat,
  isSelected,
  onClick
}) => {
  const [showStats, setShowStats] = useState(false);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['chatStats', chat.id],
    queryFn: () => chatAPI.getChatStats(chat.id),
    enabled: showStats,
  });

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Не указано';
    return new Date(dateString).toLocaleString('ru-RU');
  };

  const getChatTypeIcon = () => {
    return chat.is_forum ?? false ? '🗂️' : '💬';
  };

  const getStatusIcon = (enabled: boolean) => {
    return enabled ? '✅' : '❌';
  };

  return (
    <div className={`chat-card ${isSelected ? 'selected' : ''}`}>
      <div className="chat-card-header">
        <label className="chat-select" style={{ opacity: 0.5 }} title="Bulk actions temporarily disabled">
          <input
            type="checkbox"
            checked={false}
            disabled={true}
            onClick={(e) => e.stopPropagation()}
          />
        </label>

        <div className="chat-info" onClick={onClick}>
          <div className="chat-title">
            <span className="chat-icon">{getChatTypeIcon()}</span>
            <span className="title-text">
              {chat.title || `Чат ${chat.id}`}
            </span>
          </div>
          <div className="chat-id">ID: {chat.id}</div>
        </div>

        <button
          className="stats-toggle"
          onClick={(e) => {
            e.stopPropagation();
            setShowStats(!showStats);
          }}
        >
          {showStats ? '🔽' : '▶️'}
        </button>
      </div>

      <div className="chat-card-body">
        <div className="chat-features">
          <div className="feature">
            <span className="feature-label">Приветствие:</span>
            <span className="feature-status">
              {getStatusIcon(chat.is_welcome_enabled ?? false)}
              {(chat.is_welcome_enabled ?? false) && chat.welcome_message && (
                <span className="feature-detail">
                  (удаление через {chat.welcome_delete_time ?? 0}с)
                </span>
              )}
            </span>
          </div>

          <div className="feature">
            <span className="feature-label">Капча:</span>
            <span className="feature-status">
              {getStatusIcon(chat.is_captcha_enabled ?? false)}
            </span>
          </div>
        </div>

        {chat.welcome_message && (
          <div className="welcome-preview">
            <div className="welcome-label">Текст приветствия:</div>
            <div className="welcome-text">
              {chat.welcome_message.length > 100
                ? `${chat.welcome_message.substring(0, 100)}...`
                : chat.welcome_message
              }
            </div>
          </div>
        )}

        {showStats && (
          <div className="chat-stats">
            {statsLoading ? (
              <div className="stats-loading">Загрузка статистики...</div>
            ) : stats ? (
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Участники:</span>
                  <span className="stat-value">{stats.member_count}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Сообщения (24ч):</span>
                  <span className="stat-value">{stats.message_count_24h}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Активные (24ч):</span>
                  <span className="stat-value">{stats.active_users_24h}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Модерация (24ч):</span>
                  <span className="stat-value">{stats.moderation_actions_24h}</span>
                </div>
              </div>
            ) : (
              <div className="stats-error">Ошибка загрузки статистики</div>
            )}
          </div>
        )}

        <div className="chat-timestamps">
          <div className="timestamp">
            <span className="timestamp-label">Создан:</span>
            <span className="timestamp-value">{formatDate(chat.created_at)}</span>
          </div>
          <div className="timestamp">
            <span className="timestamp-label">Изменен:</span>
            <span className="timestamp-value">{formatDate(chat.modified_at ?? chat.updated_at)}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatCard;
