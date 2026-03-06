# Agent Memory and Learning Systems Research

> Research compiled March 2026. Based on knowledge of the ecosystem as of mid-2025.
> Web access was unavailable during compilation; verify version numbers and links before implementation.

## Table of Contents

1. [Agent Memory Architectures](#1-agent-memory-architectures)
2. [RAG for Agents](#2-rag-retrieval-augmented-generation-for-agents)
3. [Feedback Learning Loops](#3-feedback-learning-loops)
4. [Tools and Libraries Comparison](#4-tools-and-libraries-comparison)
5. [pgvector vs Dedicated Vector DBs](#5-pgvector-vs-dedicated-vector-dbs)
6. [Recommendations for Our Stack](#6-recommendations-for-our-stack)

---

## 1. Agent Memory Architectures

### Memory Taxonomy

Agent memory systems broadly fall into four categories, modeled after human cognition:

| Memory Type | Duration | Purpose | Example in Our Bot |
|---|---|---|---|
| **Working/Buffer** | Single request | Current conversation context | Current admin command context |
| **Short-term (Episodic)** | Session/hours | Recent interactions, conversation history | Last N admin decisions in a session |
| **Long-term (Semantic)** | Persistent | Facts, preferences, learned knowledge | "Admin X prefers formal tone", source quality scores |
| **Procedural** | Persistent | Learned workflows and patterns | "When spam detected in chat Y, always mute first" |

### Storage Backends by Memory Type

**Working Memory:** In-process state (Python dicts, dataclasses). No persistence needed.

**Short-term / Episodic Memory:**
- **Vector stores** (pgvector, Qdrant, Chroma) -- store embeddings of recent interactions for similarity search
- **Key-value stores** (Redis) -- fast access to recent session data with TTL expiry
- **SQL tables** -- structured event logs with timestamps

**Long-term / Semantic Memory:**
- **Vector stores** -- embedding-based retrieval of facts, preferences, documents
- **Knowledge graphs** (Neo4j, or PostgreSQL with recursive CTEs + JSONB) -- relationships between entities (topics, sources, admins, chats)
- **SQL tables** -- structured preference records, quality scores, decision history

**Procedural Memory:**
- **Prompt templates** -- learned patterns encoded as system prompts
- **Configuration tables** -- rules derived from historical decisions

### Architecture Patterns

#### Pattern 1: Flat Vector Store (Simple)
All memory goes into a single vector store. Retrieval is purely similarity-based.
- **Pros:** Simple to implement, works out of the box with LangChain/LlamaIndex
- **Cons:** No structure, hard to distinguish memory types, stale data accumulates, poor for structured queries ("show me all decisions for chat X")

#### Pattern 2: Tiered Memory (MemGPT/Letta approach)
Inspired by OS virtual memory -- main context (working), recall storage (searchable archive), archival storage (long-term).
- **Pros:** Efficient context window usage, agent controls its own memory
- **Cons:** Complex, agent must learn to manage memory effectively, extra LLM calls for memory management

#### Pattern 3: Hybrid Structured + Vector (Recommended)
Combine SQL tables for structured data (preferences, scores, decisions) with vector search for unstructured retrieval (conversation history, document context).
- **Pros:** Best of both worlds, can query by exact fields AND by semantic similarity
- **Cons:** More complex schema, need to keep both stores in sync

#### Pattern 4: Knowledge Graph + Vector
Use a knowledge graph for entity relationships with vector embeddings on nodes for semantic search.
- **Pros:** Rich relationship queries, good for "what does admin X think about topic Y in chat Z"
- **Cons:** Knowledge graph maintenance is complex, Neo4j adds operational burden

### Recommendation for Our Stack

**Use Pattern 3: Hybrid Structured + Vector.** We already have PostgreSQL with SQLAlchemy. Adding pgvector gives us vector search without new infrastructure. SQL tables handle structured data (admin preferences, source scores, decision logs). Vector columns handle semantic retrieval (finding similar past decisions, relevant context).

---

## 2. RAG (Retrieval-Augmented Generation) for Agents

### Core RAG Pipeline

```
Query -> Embedding -> Vector Search -> Reranking -> Context Assembly -> LLM Generation
```

### Embedding Models (as of 2025)

| Model | Dimensions | Quality | Speed | Notes |
|---|---|---|---|---|
| `text-embedding-3-small` (OpenAI) | 1536 | Good | Fast | Cost-effective, good default |
| `text-embedding-3-large` (OpenAI) | 3072 | Excellent | Medium | Best quality from OpenAI |
| `nomic-embed-text-v1.5` | 768 | Very Good | Fast | Open-source, Matryoshka support |
| `BAAI/bge-m3` | 1024 | Excellent | Medium | Multilingual, open-source |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | Good | Very Fast | Lightweight, local inference |
| `voyage-3` (Voyage AI) | 1024 | Excellent | Fast | Strong for code and retrieval |

**For our use case (multilingual CZ/RU/EN):** `BAAI/bge-m3` or `text-embedding-3-small` are good choices. BGE-M3 excels at multilingual retrieval. If using OpenRouter already, check if they offer embedding endpoints.

### Chunking Strategies

| Strategy | Best For | Chunk Size |
|---|---|---|
| **Fixed-size** | Simple documents | 256-512 tokens with 50-token overlap |
| **Semantic** | Mixed content | Split on topic boundaries using embeddings |
| **Sentence-based** | Conversational data | Group 3-5 sentences |
| **Recursive character** | General purpose | LangChain default, splits on `\n\n`, `\n`, `. `, ` ` |
| **Parent-child** | Documents with hierarchy | Small chunks for retrieval, return parent for context |

**For admin decisions/chat messages:** Sentence-based or small fixed-size (128-256 tokens). Messages are short; we want precise retrieval.

**For source articles/documents:** Recursive character with 512-token chunks and 64-token overlap. Use parent-child if articles have clear structure.

### Reranking

Reranking dramatically improves retrieval quality (often +10-20% accuracy). The flow:
1. Vector search returns top-K candidates (K=20-50)
2. Reranker scores each candidate against the query
3. Return top-N (N=3-5) for context

**Reranking models:**
- `Cohere rerank-v3.5` -- production-grade, API-based
- `BAAI/bge-reranker-v2-m3` -- open-source, multilingual, run locally
- `cross-encoder/ms-marco-MiniLM-L-6-v2` -- lightweight, good for low-latency

### Keeping RAG Context Fresh

| Problem | Solution |
|---|---|
| Stale embeddings | Re-embed on content update; use update timestamps |
| Growing index | Partition by time period; archive old data |
| Relevance drift | Track retrieval feedback; re-rank based on usage |
| Context window limits | Summarize old conversations; compress history |

**Practical approach for our bot:**
- Store admin decisions with timestamps; weight recent decisions higher
- Source quality scores update in real-time; no need to re-embed
- Conversation summaries generated periodically (daily/weekly) replace raw history
- Use metadata filtering (chat_id, admin_id, date range) before vector search

---

## 3. Feedback Learning Loops

### The Challenge

We want the agent to learn from admin corrections WITHOUT fine-tuning the LLM. This is "RLHF-lite" -- learning from human feedback at the application layer.

### Pattern 1: Preference Database (Recommended)

Store admin approve/reject decisions as structured data. Use them to condition future prompts.

```python
# Schema concept
class AdminDecision:
    admin_id: int
    chat_id: int
    content_hash: str
    decision: Literal["approve", "reject", "edit"]
    original_content: str
    edited_content: str | None  # if edited
    context: dict  # topic, source, etc.
    timestamp: datetime
```

**How it works:**
1. Agent generates content/decision
2. Admin approves, rejects, or edits
3. Decision stored in DB with full context
4. On future generations, retrieve similar past decisions via RAG
5. Include them in prompt as few-shot examples: "In similar situations, Admin X preferred..."

**Pros:** No fine-tuning needed, transparent, auditable, works with any LLM
**Cons:** Increases prompt length, limited by context window

### Pattern 2: Reward Scoring

Assign numerical scores to outcomes and use them to adjust behavior.

```python
class SourceQualityScore:
    source_id: str
    relevance_scores: list[float]  # rolling window
    admin_approval_rate: float     # approved / total
    auto_disable_threshold: float  # disable if below 0.3
    last_updated: datetime
```

**How it works:**
1. Track approval rate per source over time
2. Sources below threshold get auto-disabled or deprioritized
3. Surface quality metrics in admin dashboard
4. No LLM involvement -- pure statistical tracking

### Pattern 3: Constitutional AI Patterns

Define explicit rules from admin feedback that override LLM behavior.

```python
# Rules derived from admin corrections
LEARNED_RULES = [
    "Never include sources from domain X (rejected 5 times)",
    "For chat Y, always use formal Czech language",
    "Summarize articles under 200 words for chat Z",
    "Admin A prefers bullet points over paragraphs",
]
```

**How it works:**
1. Analyze patterns in admin corrections
2. Extract rules (manually or via LLM summarization)
3. Add rules to system prompt as hard constraints
4. Periodically review and update rules

### Pattern 4: Embedding-Based Preference Matching

Use embeddings to find the most similar past situation and mirror the admin's decision.

```
New content -> Embed -> Find nearest past decisions ->
If all similar past decisions were "reject" -> Auto-reject (or flag)
If all similar past decisions were "approve" -> Auto-approve (or boost confidence)
If mixed -> Present to admin with context
```

### Combining Patterns (Recommended Approach)

1. **Source scoring (Pattern 2)** for source quality tracking -- simple, effective, no LLM cost
2. **Preference database (Pattern 1)** for admin style/tone preferences -- few-shot examples in prompts
3. **Constitutional rules (Pattern 3)** for hard constraints learned from repeated corrections
4. **Embedding matching (Pattern 4)** for auto-confidence scoring on new content

### Implementation Priority

| Phase | What | Complexity | Impact |
|---|---|---|---|
| 1 | Source quality scoring (approve/reject rates) | Low | High |
| 2 | Decision logging with full context | Low | Medium (enables future learning) |
| 3 | Few-shot examples from past decisions in prompts | Medium | High |
| 4 | Auto-confidence scoring via embedding similarity | Medium | Medium |
| 5 | Rule extraction from correction patterns | High | Medium |

---

## 4. Tools and Libraries Comparison

### Memory-Focused Libraries

| Library | Version (2025) | Memory Types | Vector Store | Production Ready | Async | Notes |
|---|---|---|---|---|---|---|
| **Mem0** | 0.1.x | Semantic, episodic | Qdrant, Chroma, pgvector | Growing | Partial | Managed service + OSS. Auto-extracts "memories" from conversations. |
| **Zep** | 2.x | Facts, sessions, knowledge graph | Built-in (Postgres-based) | Yes | Yes | Best structured memory. Extracts facts automatically. Has knowledge graph. |
| **Letta (MemGPT)** | 0.5.x | Tiered (core, recall, archival) | Chroma, Qdrant, pgvector | Growing | Partial | Agent manages its own memory. Most autonomous approach. |
| **LangChain Memory** | 0.2.x | Buffer, summary, entity, vector | Any supported | Yes | Yes | Framework-coupled. Many memory types but shallow. |
| **LlamaIndex** | 0.11.x | Chat, vector, composable | Any supported | Yes | Yes | Best for document-heavy RAG. Strong indexing. |

### Detailed Comparison

#### Mem0

- **Approach:** Automatically extracts "memories" (facts, preferences) from conversations
- **Architecture:** Takes conversation input, uses LLM to extract memories, stores in vector DB
- **Strengths:** Simple API (`m.add()`, `m.search()`), auto-extraction, managed cloud option
- **Weaknesses:** Limited structured query support, relatively new, extraction quality depends on LLM
- **Python integration:** `pip install mem0ai`
- **Async:** Limited async support as of 2025
- **Our fit:** Good for extracting admin preferences automatically, but we may want more control

```python
from mem0 import Memory
m = Memory()
m.add("Admin prefers formal Czech in chat X", user_id="admin_123")
results = m.search("language preference for chat X", user_id="admin_123")
```

#### Zep

- **Approach:** Session-based memory with automatic fact extraction and knowledge graphs
- **Architecture:** Ingests conversation sessions, extracts facts, builds entity graph, provides retrieval
- **Strengths:** Production-grade, async Python SDK, knowledge graph, structured fact extraction, built on Postgres
- **Weaknesses:** Requires Zep server (self-hosted or cloud), heavier infrastructure
- **Python integration:** `pip install zep-python`
- **Async:** Full async support
- **Our fit:** Strong candidate. Fact extraction + knowledge graph fits admin preference tracking well. Postgres-based aligns with our stack.

```python
from zep_python.client import AsyncZep
client = AsyncZep(api_key="...", base_url="...")
session = await client.memory.add_session(session_id="admin_123_session")
await client.memory.add(session_id=session.id, messages=[...])
facts = await client.memory.get_session_facts(session_id=session.id)
```

#### Letta (formerly MemGPT)

- **Approach:** Agent with self-managed memory, inspired by OS virtual memory
- **Architecture:** Core memory (in-context), recall memory (searchable conversation history), archival memory (long-term vector store)
- **Strengths:** Most autonomous -- agent decides what to remember/forget, handles context window limits gracefully
- **Weaknesses:** Complex, many LLM calls for memory management, harder to control/audit, still maturing
- **Python integration:** `pip install letta`
- **Async:** Partial
- **Our fit:** Interesting for fully autonomous agents, but overkill for our current needs. Memory management overhead is significant.

#### LangChain Memory

- **Types available:** ConversationBufferMemory, ConversationSummaryMemory, ConversationEntityMemory, VectorStoreRetrieverMemory, ConversationKGMemory
- **Strengths:** Many options, well-documented, framework integration
- **Weaknesses:** Tightly coupled to LangChain ecosystem, often shallow implementations, "works for demos but needs customization for production"
- **Our fit:** We use PydanticAI, not LangChain. Could use individual components but adds framework dependency.

#### LlamaIndex

- **Approach:** Document-centric indexing and retrieval with composable indices
- **Strengths:** Best-in-class document ingestion, multiple index types, strong RAG pipeline
- **Weaknesses:** Document-focused (less about conversational memory), heavy dependency tree
- **Our fit:** Good if we need to ingest and index source articles/documents. Less relevant for admin preference memory.

### Verdict

For our use case (admin preferences, source quality, decision history):

1. **Best fit: Custom implementation with pgvector** -- we already have PostgreSQL, SQLAlchemy, and domain-specific needs. Build structured tables for decisions/scores, add pgvector for semantic search.
2. **If we want a memory library: Zep** -- production-grade, async, Postgres-based, fact extraction, knowledge graph.
3. **For document RAG specifically: LlamaIndex** -- if we need to ingest and search source articles.

---

## 5. pgvector vs Dedicated Vector DBs

### Comparison Matrix

| Feature | pgvector | Qdrant | Chroma | Pinecone | Milvus |
|---|---|---|---|---|---|
| **Deployment** | PostgreSQL extension | Self-hosted / Cloud | Embedded / Server | Cloud only | Self-hosted / Cloud |
| **Max vectors** | Millions (practical) | Billions | Millions | Billions | Billions |
| **Index types** | IVFFlat, HNSW | HNSW | HNSW | Proprietary | IVFFlat, HNSW, DiskANN |
| **Filtering** | Full SQL WHERE | Payload filters | Metadata filters | Metadata filters | Attribute filters |
| **ACID transactions** | Yes (PostgreSQL) | No | No | No | No |
| **Async Python** | Via asyncpg/SQLAlchemy | Yes (qdrant-client) | No (sync only) | Yes | Yes |
| **Ops overhead** | None (existing PG) | New service | Minimal (embedded) | None (managed) | New service |
| **Cost** | Free (PG extension) | Free (OSS) / paid cloud | Free (OSS) | Pay per usage | Free (OSS) / paid |
| **SQLAlchemy support** | Native (pgvector lib) | N/A | N/A | N/A | N/A |
| **Hybrid search** | Yes (SQL + vector) | Yes (BM25 + vector) | Limited | Limited | Yes |

### pgvector Details

**Supported operations:**
- L2 distance (`<->`)
- Inner product (`<#>`)
- Cosine distance (`<=>`)
- L1 distance (`<+>`, v0.7+)

**Index types:**
- **IVFFlat:** Faster build, lower recall. Good for < 1M vectors.
- **HNSW:** Slower build, higher recall. Recommended for production. Available since pgvector 0.5.

**SQLAlchemy integration:**
```python
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Integer
from sqlalchemy.orm import DeclarativeBase

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    content = Column(Text)
    embedding = Column(Vector(1536))  # dimension matches model
```

**Performance (approximate, mid-2025 benchmarks):**
- 1M vectors, 1536 dimensions, HNSW: ~5-15ms query time
- 10M vectors: ~20-50ms query time (still fast for our use case)
- Dedicated vector DBs (Qdrant, Milvus) are ~2-5x faster at 10M+ scale

### When pgvector Is Sufficient

- Vector count under 5-10 million
- Query latency requirements > 10ms (typical for our bot -- not real-time search)
- Already using PostgreSQL (no new infrastructure)
- Need ACID transactions across vector and relational data
- Need complex SQL filtering alongside vector search
- Team size is small (fewer services to maintain)

### When to Consider a Dedicated Vector DB

- Vector count exceeds 10M+ and growing rapidly
- Sub-millisecond query latency required
- Advanced features needed: multi-tenancy, sharding, real-time indexing at scale
- Separate scaling of vector search from relational DB
- Need specialized features like sparse vectors, multi-vector search

### Recommendation for Our Stack

**Use pgvector.** Rationale:

1. **Scale:** Our bot manages educational chats in CZ. Even with years of data, we are unlikely to exceed 1M vectors. pgvector handles this easily.
2. **Infrastructure:** We already run PostgreSQL 17.6. Adding pgvector is `CREATE EXTENSION vector;` -- zero new services.
3. **Transactions:** We need decisions, preferences, and embeddings in the same transaction. pgvector gives us this natively.
4. **SQLAlchemy:** The `pgvector` Python library integrates directly with SQLAlchemy 2.x async, matching our stack perfectly.
5. **Hybrid queries:** We can filter by `chat_id`, `admin_id`, `date_range` AND do similarity search in one query.
6. **Operational cost:** No new service to deploy, monitor, backup, or upgrade.

**Migration path:** If we ever outgrow pgvector, Qdrant is the best upgrade path -- open-source, async Python client, excellent performance. But this is unlikely for our scale.

---

## 6. Recommendations for Our Stack

### Architecture Overview

```
+------------------+     +------------------+     +------------------+
|  Telegram Bot    |     |  Agent Core      |     |  PostgreSQL      |
|  (aiogram 3.x)  |---->|  (PydanticAI)    |---->|  + pgvector      |
|                  |     |                  |     |                  |
|  Handlers        |     |  Memory Manager  |     |  Tables:         |
|  Middlewares     |     |  Decision Logger |     |  - decisions     |
|  Callbacks       |     |  Source Scorer   |     |  - preferences   |
+------------------+     |  RAG Retriever   |     |  - source_scores |
                         +------------------+     |  - embeddings    |
                                                  +------------------+
```

### Implementation Plan

#### Phase 1: Foundation (Week 1-2)

**1. Add pgvector to PostgreSQL**
```sql
CREATE EXTENSION vector;
```

**2. Create core tables via Alembic migration**

```python
# Decision log -- records every admin approve/reject/edit
class AgentDecisionLog(Base):
    __tablename__ = "agent_decision_log"
    id = Column(Integer, primary_key=True)
    agent_action = Column(String)  # "generate_post", "moderate", "summarize"
    chat_id = Column(BigInteger, index=True)
    admin_id = Column(BigInteger, index=True)
    decision = Column(String)  # "approve", "reject", "edit"
    original_content = Column(Text)
    final_content = Column(Text, nullable=True)
    context_json = Column(JSONB)  # topic, source, tags
    embedding = Column(Vector(768))  # for similarity search
    created_at = Column(DateTime, default=func.now())

# Source quality tracking
class SourceQualityScore(Base):
    __tablename__ = "source_quality_scores"
    id = Column(Integer, primary_key=True)
    source_identifier = Column(String, unique=True, index=True)
    total_uses = Column(Integer, default=0)
    approvals = Column(Integer, default=0)
    rejections = Column(Integer, default=0)
    approval_rate = Column(Float, default=0.0)
    is_disabled = Column(Boolean, default=False)
    last_used_at = Column(DateTime)

# Admin preferences (extracted facts)
class AdminPreference(Base):
    __tablename__ = "admin_preferences"
    id = Column(Integer, primary_key=True)
    admin_id = Column(BigInteger, index=True)
    chat_id = Column(BigInteger, nullable=True)  # null = global
    preference_type = Column(String)  # "tone", "length", "format", "topic"
    preference_value = Column(Text)
    confidence = Column(Float, default=0.5)
    source_decisions = Column(JSONB)  # decision IDs that led to this
    embedding = Column(Vector(768))
    updated_at = Column(DateTime, default=func.now())
```

**3. Install dependencies**
```bash
uv add pgvector sqlalchemy[asyncio]
# For embeddings (pick one):
uv add sentence-transformers  # local, free, fast
# OR use OpenRouter/OpenAI embedding API
```

#### Phase 2: Decision Logging & Source Scoring (Week 2-3)

- Log every agent action + admin response in `AgentDecisionLog`
- Compute and update `SourceQualityScore` on each approve/reject
- Auto-disable sources with approval rate < 0.3 after 10+ uses
- Add admin dashboard endpoint showing source quality metrics

#### Phase 3: RAG-Powered Context (Week 3-4)

- Generate embeddings for new decisions (async, background)
- Before agent generates content, retrieve top-5 similar past decisions for the same chat
- Include past decisions as few-shot examples in agent prompt
- Implement metadata-filtered vector search: `WHERE chat_id = X AND decision = 'approve' ORDER BY embedding <=> query_embedding LIMIT 5`

#### Phase 4: Preference Extraction (Week 4-5)

- Periodically (or on threshold) analyze decision patterns per admin
- Extract preferences via LLM: "Given these 20 approved and 10 rejected posts for admin X in chat Y, what are their preferences?"
- Store as `AdminPreference` records
- Include relevant preferences in agent system prompt

### Technology Choices Summary

| Component | Choice | Rationale |
|---|---|---|
| Vector store | **pgvector** | Already use PostgreSQL, sufficient scale, ACID, SQLAlchemy integration |
| Embedding model | **sentence-transformers** (local) or **text-embedding-3-small** (API) | Local is free and fast; API is simpler. Start local, switch if quality insufficient |
| Memory framework | **Custom (no library)** | Our needs are specific; libraries add complexity without clear benefit |
| RAG reranking | **BAAI/bge-reranker-v2-m3** (optional, Phase 3+) | Add only if retrieval quality needs improvement |
| Feedback loop | **Structured logging + statistical scoring** | Simple, effective, auditable |
| Knowledge graph | **PostgreSQL JSONB + recursive CTEs** (if needed) | Avoid Neo4j unless graph queries become complex |

### Key Dependencies to Add

```toml
# pyproject.toml additions
[project.dependencies]
pgvector = ">=0.3.0"
sentence-transformers = ">=3.0.0"  # if using local embeddings
# OR
openai = ">=1.0.0"  # if using OpenAI embeddings via API
```

### Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Embedding quality for CZ/RU text | Use multilingual model (bge-m3); test with real data before committing |
| pgvector performance at scale | Monitor query times; HNSW index; partition by chat_id if needed |
| Prompt length with few-shot examples | Limit to 3-5 examples; summarize old decisions; use relevance threshold |
| Over-fitting to admin preferences | Require minimum N decisions before extracting preferences; allow admin override |
| Embedding model changes | Store model name with embeddings; re-embed on model change (migration script) |

---

## Appendix: Key Resources

### Documentation
- pgvector: https://github.com/pgvector/pgvector
- pgvector Python: https://github.com/pgvector/pgvector-python
- Mem0: https://docs.mem0.ai
- Zep: https://docs.getzep.com
- Letta: https://docs.letta.com
- LangChain Memory: https://python.langchain.com/docs/modules/memory/
- LlamaIndex: https://docs.llamaindex.ai
- Sentence Transformers: https://www.sbert.net
- PydanticAI: https://ai.pydantic.dev

### Research Papers
- "MemGPT: Towards LLMs as Operating Systems" (Packer et al., 2023) -- tiered memory architecture
- "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (Lewis et al., 2020) -- foundational RAG paper
- "Self-RAG: Learning to Retrieve, Generate, and Critique" (Asai et al., 2023) -- adaptive retrieval
- "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval" (Sarthi et al., 2024) -- hierarchical summarization for RAG

### Benchmarks
- MTEB Leaderboard (Massive Text Embedding Benchmark): https://huggingface.co/spaces/mteb/leaderboard
- ANN Benchmarks (vector search performance): https://ann-benchmarks.com
