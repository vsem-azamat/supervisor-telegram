import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { chatAPI } from '../services/api';
import type { ChatUpdateData } from '../types/chat';

interface ChatBulkActionsProps {
  selectedChatIds: number[];
  onActionComplete: () => void;
}

const ChatBulkActions: React.FC<ChatBulkActionsProps> = ({
  selectedChatIds,
  onActionComplete,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [updateData, setUpdateData] = useState<ChatUpdateData>({});

  const bulkUpdateMutation = useMutation({
    mutationFn: (data: ChatUpdateData) => {
      const config = {
        actionType: 'bulk_update',
        values: data as Record<string, unknown>,
        applyTo: 'selected' as const,
        confirmationRequired: false
      }
      return chatAPI.bulkUpdateChats(selectedChatIds, config)
    },
    onSuccess: () => {
      onActionComplete();
      setUpdateData({});
      setIsExpanded(false);
    },
  });

  const handleBulkUpdate = () => {
    if (Object.keys(updateData).length === 0) {
      alert('Выберите настройки для изменения');
      return;
    }

    const confirmMessage = `Применить изменения к ${selectedChatIds.length} чатам?`;
    if (confirm(confirmMessage)) {
      bulkUpdateMutation.mutate(updateData);
    }
  };

  // Quick actions temporarily disabled until bulk update API is fully implemented
  const quickActions: Array<{label: string; action: () => void}> = [];

  return (
    <div className="bulk-actions">
      <div className="bulk-actions-header">
        <h3>Массовые действия ({selectedChatIds.length} чатов)</h3>
        <button
          className="expand-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? 'Свернуть' : 'Развернуть'}
        </button>
      </div>

      {quickActions.length > 0 && (
        <div className="quick-actions">
          {quickActions.map((action, index) => (
            <button
              key={index}
              className="quick-action-btn"
              onClick={action.action}
              disabled={bulkUpdateMutation.isPending}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      {isExpanded && (
        <div className="detailed-actions">
          <div className="bulk-form">
            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={updateData.is_welcome_enabled !== undefined}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setUpdateData(prev => ({ ...prev, is_welcome_enabled: true }));
                    } else {
                      const { is_welcome_enabled, ...rest } = updateData;
                      void is_welcome_enabled; // Suppress unused warning
                      setUpdateData(rest);
                    }
                  }}
                />
                Приветствие
              </label>
              {updateData.is_welcome_enabled !== undefined && (
                <select
                  value={updateData.is_welcome_enabled ? 'true' : 'false'}
                  onChange={(e) => setUpdateData(prev => ({
                    ...prev,
                    is_welcome_enabled: e.target.value === 'true'
                  }))}
                >
                  <option value="true">Включено</option>
                  <option value="false">Отключено</option>
                </select>
              )}
            </div>

            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={updateData.is_captcha_enabled !== undefined}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setUpdateData(prev => ({ ...prev, is_captcha_enabled: true }));
                    } else {
                      const { is_captcha_enabled, ...rest } = updateData;
                      void is_captcha_enabled; // Suppress unused warning
                      setUpdateData(rest);
                    }
                  }}
                />
                Капча
              </label>
              {updateData.is_captcha_enabled !== undefined && (
                <select
                  value={updateData.is_captcha_enabled ? 'true' : 'false'}
                  onChange={(e) => setUpdateData(prev => ({
                    ...prev,
                    is_captcha_enabled: e.target.value === 'true'
                  }))}
                >
                  <option value="true">Включена</option>
                  <option value="false">Отключена</option>
                </select>
              )}
            </div>

            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={updateData.welcome_delete_time !== undefined}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setUpdateData(prev => ({ ...prev, welcome_delete_time: 60 }));
                    } else {
                      const { welcome_delete_time, ...rest } = updateData;
                      void welcome_delete_time; // Suppress unused warning
                      setUpdateData(rest);
                    }
                  }}
                />
                Время удаления приветствия (секунды)
              </label>
              {updateData.welcome_delete_time !== undefined && (
                <input
                  type="number"
                  min="1"
                  value={updateData.welcome_delete_time}
                  onChange={(e) => setUpdateData(prev => ({
                    ...prev,
                    welcome_delete_time: parseInt(e.target.value)
                  }))}
                />
              )}
            </div>

            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={updateData.welcome_message !== undefined}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setUpdateData(prev => ({ ...prev, welcome_message: '' }));
                    } else {
                      const { welcome_message, ...rest } = updateData;
                      void welcome_message; // Suppress unused warning
                      setUpdateData(rest);
                    }
                  }}
                />
                Текст приветствия
              </label>
              {updateData.welcome_message !== undefined && (
                <textarea
                  value={updateData.welcome_message}
                  onChange={(e) => setUpdateData(prev => ({
                    ...prev,
                    welcome_message: e.target.value
                  }))}
                  placeholder="Введите текст приветствия..."
                  rows={3}
                />
              )}
            </div>

            <button
              className="apply-bulk-btn"
              onClick={handleBulkUpdate}
              disabled={true}
              title="Функция временно отключена"
            >
              Применить изменения (отключено)
            </button>
          </div>
        </div>
      )}

      {bulkUpdateMutation.error && (
        <div className="bulk-error">
          Ошибка: {bulkUpdateMutation.error.message}
        </div>
      )}
    </div>
  );
};

export default ChatBulkActions;
