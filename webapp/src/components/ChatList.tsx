import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { chatAPI } from '../services/api';
import type { Chat } from '../types';
import ChatCard from './ChatCard';
// import ChatBulkActions from './ChatBulkActions'; // Temporarily disabled

interface ChatListProps {
  onChatSelect?: (chat: Chat) => void;
}

const ChatList: React.FC<ChatListProps> = ({ onChatSelect }) => {
  const [selectedChats, setSelectedChats] = useState<number[]>([]);
  const [searchTerm, setSearchTerm] = useState('');

  const {
    data: chats,
    isLoading,
    error,
    refetch
  } = useQuery({
    queryKey: ['chats'],
    queryFn: chatAPI.getChats,
    retry: 3, // Retry failed requests 3 times
    refetchOnWindowFocus: false,
  });

  // Ensure chats is always an array
  const safeChats = Array.isArray(chats) ? chats : [];

  const filteredChats = safeChats.filter(chat =>
    chat.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    chat.id.toString().includes(searchTerm)
  );

  const handleChatSelect = (chatId: number, selected: boolean) => {
    setSelectedChats(prev =>
      selected
        ? [...prev, chatId]
        : prev.filter(id => id !== chatId)
    );
  };

  // const handleSelectAll = () => {
  //   setSelectedChats(
  //     selectedChats.length === filteredChats.length
  //       ? []
  //       : filteredChats.map(chat => chat.id)
  //   );
  // };

  if (isLoading) {
    return (
      <div className="chat-list-loading">
        <p>Загрузка чатов...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="chat-list-error">
        <p>Ошибка при загрузке чатов: {error.message}</p>
        <button onClick={() => refetch()}>Попробовать снова</button>
      </div>
    );
  }

  return (
    <div className="chat-list">
      <div className="chat-list-header">
        <h2>Управление чатами ({filteredChats.length})</h2>

        <div className="chat-search">
          <input
            type="text"
            placeholder="Поиск по названию или ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="search-input"
          />
        </div>

        <div className="selection-controls" style={{ opacity: 0.5 }}>
          <label className="checkbox-label" title="Bulk selection temporarily disabled">
            <input
              type="checkbox"
              checked={false}
              disabled={true}
            />
            Выбрать все (отключено)
          </label>
        </div>
      </div>

      {/* Bulk actions temporarily disabled
      {selectedChats.length > 0 && (
        <ChatBulkActions
          selectedChatIds={selectedChats}
          onActionComplete={() => {
            setSelectedChats([]);
            refetch();
          }}
        />
      )}
      */}

      <div className="chat-grid">
        {filteredChats.map(chat => (
          <ChatCard
            key={chat.id}
            chat={chat}
            isSelected={selectedChats.includes(chat.id)}
            onSelect={(selected) => handleChatSelect(chat.id, selected)}
            onClick={() => onChatSelect?.(chat)}
          />
        ))}
      </div>

      {filteredChats.length === 0 && searchTerm && (
        <div className="no-results">
          <p>Чаты не найдены по запросу "{searchTerm}"</p>
        </div>
      )}

      {safeChats.length === 0 && !searchTerm && (
        <div className="no-chats">
          <p>Нет доступных чатов</p>
        </div>
      )}
    </div>
  );
};

export default ChatList;
