# Services Layer Architecture

This directory contains the frontend API integration layer with clear separation of concerns.

## 📁 File Structure

```
services/
├── apiClient.ts      # Low-level HTTP client (infrastructure)
├── api.ts            # Chat management API (domain service)
└── agentApi.ts       # AI agent API (domain service)
```

---

## 🏗️ Architecture Pattern: Separation of Concerns

### **apiClient.ts** - Infrastructure Layer

**Purpose:** Low-level HTTP client configuration and authentication

**Responsibilities:**
- Configure axios instance (base URL, timeouts, headers)
- Handle Telegram WebApp authentication (add `X-Telegram-Init-Data` header)
- Global request/response interceptors
- Error handling (401, 403, etc.)

**What it provides:**
```typescript
export const apiClient  // Pre-configured axios instance
```

**Why it exists:**
- ✅ **Single source of truth** for authentication logic
- ✅ **DRY principle** - authentication code written once, used everywhere
- ✅ **Easy to test** - mock apiClient instead of axios
- ✅ **Easy to change** - switch from axios to fetch without touching business logic

**Example:**
```typescript
// Automatically adds X-Telegram-Init-Data to every request
apiClient.interceptors.request.use((config) => {
  config.headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData
  return config
})
```

---

### **api.ts** - Domain Service (Chat Management)

**Purpose:** High-level API for chat and moderation operations

**Responsibilities:**
- Define domain-specific API methods (`getChats`, `updateChat`, `bulkUpdateChats`)
- Type conversions (backend API types → frontend domain types)
- Business logic (field mapping, validation)
- Error messages in user-friendly format

**What it provides:**
```typescript
export const apiService  // Chat management service
export const chatAPI     // Alias for backward compatibility
```

**Example:**
```typescript
class ApiService {
  private client = apiClient  // Uses shared authenticated client

  async getChats(): Promise<Chat[]> {
    const response = await this.client.get('/chats')
    return response.data.map(chat => this.convertApiChatToChat(chat))
  }
}
```

---

### **agentApi.ts** - Domain Service (AI Agent)

**Purpose:** High-level API for AI agent operations

**Responsibilities:**
- AI agent session management
- Model selection and configuration
- Chat message handling
- Domain-specific types (`AgentSession`, `AgentMessage`)

**What it provides:**
```typescript
export const agentApi  // AI agent service functions
```

**Example:**
```typescript
export const agentApi = {
  async createSession(request: CreateSessionRequest): Promise<AgentSession> {
    const response = await apiClient.post('/agent/sessions', request)
    return response.data
  }
}
```

---

## 🎯 Benefits of This Architecture

### 1. **Separation of Concerns**
```
┌─────────────────────────────────────────┐
│  Components (React UI)                  │
│  ↓ call domain methods                  │
├─────────────────────────────────────────┤
│  Domain Services (api.ts, agentApi.ts) │
│  • Business logic                       │
│  • Type conversions                     │
│  • Error handling                       │
│  ↓ use shared client                    │
├─────────────────────────────────────────┤
│  Infrastructure (apiClient.ts)          │
│  • HTTP configuration                   │
│  • Authentication                       │
│  • Global interceptors                  │
│  ↓ makes HTTP requests                  │
├─────────────────────────────────────────┤
│  Backend API (FastAPI)                  │
└─────────────────────────────────────────┘
```

### 2. **Easy Authentication Management**

**Before (without apiClient.ts):**
```typescript
// ❌ Problem: Authentication logic duplicated everywhere
// api.ts
async getChats() {
  const initData = window.Telegram.WebApp.initData
  const response = await axios.get('/api/v1/chats', {
    headers: { 'X-Telegram-Init-Data': initData }
  })
}

// agentApi.ts
async createSession() {
  const initData = window.Telegram.WebApp.initData  // Duplicated!
  const response = await axios.post('/api/v1/agent/sessions', data, {
    headers: { 'X-Telegram-Init-Data': initData }  // Duplicated!
  })
}
```

**After (with apiClient.ts):**
```typescript
// ✅ Solution: Authentication added automatically
// api.ts
async getChats() {
  const response = await apiClient.get('/chats')  // Auth added automatically!
}

// agentApi.ts
async createSession() {
  const response = await apiClient.post('/agent/sessions', data)  // Auth added automatically!
}
```

### 3. **Easy to Test**

```typescript
// Mock apiClient in tests
jest.mock('./apiClient', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  }
}))

// Test api.ts without hitting real backend
test('getChats returns converted chat list', async () => {
  apiClient.get.mockResolvedValue({ data: mockApiResponse })
  const chats = await apiService.getChats()
  expect(chats).toEqual(expectedFrontendFormat)
})
```

### 4. **Easy to Change Authentication**

Need to change auth method? Only touch `apiClient.ts`:

```typescript
// Example: Switch from header to cookie-based auth
apiClient.interceptors.request.use((config) => {
  // Only change this one file!
  const token = getCookieToken()
  config.headers['Authorization'] = `Bearer ${token}`
  return config
})
```

All API calls (`api.ts`, `agentApi.ts`) automatically use the new auth method.

---

## 📝 When to Add New Code

### Add to **apiClient.ts** when:
- ✅ Adding global request/response interceptors
- ✅ Changing authentication method
- ✅ Adding global error handling
- ✅ Changing base URL or timeout configuration
- ✅ Adding request/response logging

### Add to **api.ts** when:
- ✅ Adding new chat management endpoints
- ✅ Changing backend API response format
- ✅ Adding chat-related business logic
- ✅ Adding chat-specific error handling

### Add to **agentApi.ts** when:
- ✅ Adding new AI agent endpoints
- ✅ Adding agent-related business logic
- ✅ Changing agent session management

### Create NEW service file when:
- ✅ Adding completely new domain (e.g., `userApi.ts`, `statsApi.ts`)

---

## 🔄 Data Flow Example

### Example: User opens webapp and fetches chats

```typescript
// 1. Component calls domain service
const { data } = useQuery('chats', () => apiService.getChats())

// 2. api.ts (domain service) uses apiClient
async getChats(): Promise<Chat[]> {
  const response = await this.client.get('/chats')  // this.client is apiClient
  return response.data.map(this.convertApiChatToChat)
}

// 3. apiClient.ts (infrastructure) adds auth and makes request
apiClient.interceptors.request.use((config) => {
  // Automatically adds Telegram auth header
  config.headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData
  return config
})

// 4. Backend receives authenticated request
// GET /api/v1/chats
// Headers: { X-Telegram-Init-Data: "query_id=...&user=...&hash=..." }

// 5. Response flows back through the layers
Backend → apiClient → api.ts (converts types) → Component
```

---

## 🎯 Key Takeaways

| Aspect | apiClient.ts | api.ts / agentApi.ts |
|--------|-------------|---------------------|
| **Layer** | Infrastructure | Domain/Business Logic |
| **Concern** | How to make requests | What requests to make |
| **Knows about** | HTTP, Auth, Errors | Business entities, Types |
| **Changes when** | Auth method changes | Business requirements change |
| **Reusable** | Yes (shared by all APIs) | No (domain-specific) |
| **Testable** | Mock window.Telegram | Mock apiClient |

---

## 💡 Best Practices

### ✅ Do:
- Use `apiClient` for all HTTP requests
- Keep business logic in domain services (`api.ts`, `agentApi.ts`)
- Add new domain services for new feature areas
- Type everything with TypeScript

### ❌ Don't:
- Import `axios` directly in domain services
- Put business logic in `apiClient.ts`
- Duplicate authentication code
- Mix different domains in one service file

---

## 🚀 Future Improvements

Potential enhancements to this architecture:

1. **Request caching layer** in `apiClient.ts`
2. **Retry logic** for failed requests
3. **Request deduplication** to prevent duplicate API calls
4. **WebSocket support** for real-time updates
5. **Offline queue** for requests when offline
6. **Request cancellation** for component unmounts

All these improvements would only require changes to `apiClient.ts` without touching domain services!
