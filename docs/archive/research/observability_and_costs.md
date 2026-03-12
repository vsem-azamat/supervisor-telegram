# Observability, Cost Control, and Reliability for LLM-Powered Agent Systems

Research compiled for the moderator-bot project (Python, structlog, PostgreSQL, OpenRouter + PydanticAI).

> **Note:** This research is based on knowledge as of early 2025. Verify pricing and feature details on vendor sites before making decisions.

---

## Table of Contents

1. [LLM Observability Platforms](#1-llm-observability-platforms)
2. [Cost Optimization Strategies](#2-cost-optimization-strategies)
3. [Reliability Patterns](#3-reliability-patterns)
4. [Structured Logging for Agents](#4-structured-logging-for-agents)
5. [Budget Management](#5-budget-management)
6. [OpenRouter-Specific](#6-openrouter-specific)
7. [Recommendations for Our Stack](#7-recommendations-for-our-stack)

---

## 1. LLM Observability Platforms

### Comparison Matrix

| Platform | Self-Hosted | Free Tier | OpenRouter Compat | Key Strength |
|---|---|---|---|---|
| **Langfuse** | Yes (OSS, MIT) | 50k observations/mo | Yes (OpenAI-compat SDK) | Best OSS option, full tracing |
| **Helicone** | Yes (OSS) | 100k requests/mo | Yes (proxy-based) | Simplest setup (proxy approach) |
| **LangSmith** | No (cloud only) | 5k traces/mo | Partial (via LangChain) | Deep LangChain integration |
| **Portkey** | Yes (enterprise) | 10k requests/mo | Yes (AI gateway) | Gateway with caching + fallbacks |
| **Braintrust** | No | Free tier available | Yes (OpenAI-compat) | Strong eval/scoring focus |
| **Phoenix (Arize)** | Yes (OSS, Apache 2) | Unlimited (self-host) | Yes (OpenTelemetry) | OTel-native, great for ML teams |
| **W&B Prompts** | No | Limited free | Manual integration | Best if already using W&B |

### Platform Details

#### Langfuse (Recommended for our stack)
- **URL:** https://langfuse.com
- **License:** MIT, fully self-hostable via Docker
- **Features:** Tracing, cost tracking, prompt management, evaluations, datasets, user-level analytics
- **Python SDK:** `langfuse` package with decorators (`@observe`), works with any LLM provider
- **PydanticAI integration:** Use the Langfuse callback handler or wrap calls manually
- **OpenRouter:** Works via OpenAI-compatible SDK; set `base_url` to OpenRouter, Langfuse intercepts
- **Pricing (cloud):** Free: 50k observations/mo; Pro: $59/mo for 1M observations; Team: custom
- **Self-hosted cost:** Just PostgreSQL + a container; runs well on a small VPS

#### Helicone
- **URL:** https://helicone.ai
- **License:** Apache 2.0, self-hostable
- **Approach:** Proxy-based -- route LLM calls through Helicone's proxy URL, zero code changes
- **Features:** Cost tracking, latency monitoring, caching (exact + semantic), rate limiting, user tracking
- **OpenRouter:** Change base URL from `openrouter.ai` to `oai.helicone.ai` and add auth header
- **Pricing (cloud):** Free: 100k requests/mo; Growth: $20/mo; Enterprise: custom
- **Best for:** Teams wanting minimal code changes

#### Portkey
- **URL:** https://portkey.ai
- **Approach:** AI gateway (proxy + SDK) with built-in reliability features
- **Features:** Caching, automatic retries, fallbacks, load balancing, budget limits, guardrails
- **OpenRouter:** Can sit in front of OpenRouter or replace it entirely for multi-provider routing
- **Pricing:** Free: 10k requests/mo; Developer: $49/mo; custom tiers
- **Overlap with OpenRouter:** Portkey duplicates many OpenRouter features; using both creates redundancy

#### Phoenix (Arize)
- **URL:** https://github.com/Arize-AI/phoenix
- **License:** Apache 2.0, fully self-hostable
- **Approach:** OpenTelemetry-based instrumentation
- **Features:** Tracing, evaluations, embeddings analysis, LLM-as-judge evals
- **Best for:** Teams already using OpenTelemetry or wanting standards-based observability
- **Integration:** `openinference-instrumentation-openai` auto-instruments OpenAI-compatible calls

#### LangSmith
- **URL:** https://smith.langchain.com
- **Caveat:** Tightly coupled to LangChain ecosystem; not ideal for PydanticAI
- **Features:** Best-in-class tracing UI, prompt playground, evaluations, datasets
- **Pricing:** Free: 5k traces/mo; Plus: $39/seat/mo; Enterprise: custom
- **Skip unless:** You plan to migrate to LangChain/LangGraph

#### Braintrust
- **URL:** https://braintrust.dev
- **Focus:** Evaluation and scoring over raw observability
- **Features:** Logging, evals, prompt playground, online scoring, dataset management
- **Pricing:** Generous free tier, pay for compute
- **Best for:** Teams focused on prompt quality iteration

---

## 2. Cost Optimization Strategies

### 2.1 Caching

#### Exact Match Caching
- Cache identical prompts/responses in PostgreSQL or Redis
- **Expected savings:** 20-40% for repetitive moderation queries (e.g., same spam patterns)
- **Implementation:** Hash the prompt + model + temperature; store response with TTL
- **Our stack:** Add a `llm_cache` table in PostgreSQL with columns: `prompt_hash`, `model`, `response`, `tokens_used`, `created_at`, `ttl`

```python
# Pseudocode for our stack
import hashlib

async def cached_llm_call(prompt: str, model: str, **kwargs) -> str:
    cache_key = hashlib.sha256(f"{model}:{prompt}:{kwargs.get('temperature', 0)}".encode()).hexdigest()
    cached = await repo.get_cache(cache_key)
    if cached and not cached.is_expired:
        return cached.response
    response = await openrouter_call(prompt, model, **kwargs)
    await repo.set_cache(cache_key, response, ttl=3600)
    return response
```

#### Semantic Caching
- Use embeddings to find "similar enough" past queries
- **Tools:** Redis with vector search (RediSearch), pgvector extension, Helicone built-in
- **Savings:** Additional 10-20% on top of exact match
- **Caveat:** Adds latency (embedding computation) and complexity; likely overkill for our scale
- **Recommendation:** Start with exact match caching; add semantic caching only if cost is a problem

### 2.2 Model Routing (Cheap-First Escalation)

This is the highest-impact strategy for cost reduction.

| Strategy | Description | Typical Savings |
|---|---|---|
| **Tiered routing** | Use cheap model (Gemini Flash) for 90% of calls, escalate to expensive (Claude/GPT-4) for complex cases | 60-80% |
| **Confidence-based** | If cheap model returns low confidence, re-run with expensive model | 40-60% |
| **Task-based** | Simple classification = cheap model; nuanced moderation = expensive model | 50-70% |

**Implementation for our bot:**
```python
# In agent/core.py - route by task complexity
CHEAP_MODEL = "google/gemini-2.0-flash"      # ~$0.10/M tokens
EXPENSIVE_MODEL = "anthropic/claude-sonnet"    # ~$3.00/M tokens

async def moderate_message(message: str, context: dict) -> ModerationResult:
    # Step 1: Quick classification with cheap model
    result = await llm_call(CHEAP_MODEL, classify_prompt(message))

    # Step 2: Only escalate ambiguous cases
    if result.confidence < 0.8 or result.needs_nuance:
        result = await llm_call(EXPENSIVE_MODEL, detailed_prompt(message, context))

    return result
```

**Real-world numbers:**
- At 10k messages/day with all-GPT-4: ~$15-30/day
- With tiered routing (90% Gemini Flash, 10% Claude): ~$2-5/day
- With caching on top: ~$1-3/day

### 2.3 Prompt Optimization

- **Shorter system prompts:** Every token in the system prompt is repeated per call. Trim 500 tokens = significant savings at scale.
- **Few-shot to zero-shot:** Remove examples when the model performs well without them.
- **Structured output:** Use JSON mode / tool calling to reduce output tokens (no prose).
- **Max tokens limit:** Always set `max_tokens` to prevent runaway responses.

### 2.4 Token Budgets Per Operation

Define per-operation budgets:

| Operation | Max Input Tokens | Max Output Tokens | Model | Est. Cost/Call |
|---|---|---|---|---|
| Spam classification | 500 | 100 | Gemini Flash | $0.00006 |
| Content moderation | 1000 | 200 | Gemini Flash | $0.00012 |
| Complex escalation | 2000 | 500 | Claude Sonnet | $0.0075 |
| User appeal review | 3000 | 1000 | Claude Sonnet | $0.012 |

---

## 3. Reliability Patterns

### 3.1 Retry with Fallback Models

```python
import asyncio
from typing import List

FALLBACK_CHAIN = [
    "google/gemini-2.0-flash",
    "google/gemini-1.5-flash",
    "meta-llama/llama-3.1-8b-instruct",  # Open-source fallback
]

async def resilient_llm_call(prompt: str, models: List[str] = FALLBACK_CHAIN) -> str:
    last_error = None
    for model in models:
        for attempt in range(3):  # 3 retries per model
            try:
                return await openrouter_call(prompt, model, timeout=15)
            except RateLimitError:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            except (TimeoutError, ServerError) as e:
                last_error = e
                await asyncio.sleep(1)
                break  # Try next model
    raise LLMUnavailableError(f"All models failed: {last_error}")
```

### 3.2 Circuit Breaker Pattern

Prevent cascading failures when an LLM provider is down:

```python
import time
from dataclasses import dataclass

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    _failures: int = 0
    _last_failure: float = 0
    _state: str = "closed"  # closed, open, half-open

    def can_execute(self) -> bool:
        if self._state == "closed":
            return True
        if self._state == "open":
            if time.time() - self._last_failure > self.recovery_timeout:
                self._state = "half-open"
                return True
            return False
        return True  # half-open: allow one attempt

    def record_success(self):
        self._failures = 0
        self._state = "closed"

    def record_failure(self):
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "open"
```

### 3.3 Graceful Degradation

When AI is completely unavailable, the bot should still function:

| Scenario | Degraded Behavior |
|---|---|
| Spam detection down | Fall back to keyword/regex blocklist |
| Content moderation down | Queue messages for human review, allow through |
| User analysis down | Skip risk scoring, apply standard rules |
| All LLM providers down | Log incident, notify admins, run in "manual mode" |

**Implementation pattern:**
```python
async def moderate_with_fallback(message: Message) -> ModerationResult:
    try:
        return await ai_moderate(message)
    except LLMUnavailableError:
        logger.warning("llm_unavailable", fallback="rule_based")
        return rule_based_moderate(message)  # Keyword matching, regex patterns
```

### 3.4 Rate Limiting and Queuing

- **Per-chat rate limiting:** Max N LLM calls per chat per minute to prevent abuse
- **Global rate limiting:** Cap total LLM calls/minute based on budget
- **Queue-based architecture:** For non-urgent analysis (user profiling, trend analysis), use a task queue

```python
# Simple in-memory rate limiter (upgrade to Redis for production)
from collections import defaultdict
import time

class TokenBucketRateLimiter:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        tokens, last = self._buckets.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.rate)
        if tokens >= 1:
            self._buckets[key] = (tokens - 1, now)
            return True
        return False
```

### 3.5 Handling Provider Outages

Production patterns used by teams running LLM agents:

1. **Multi-provider diversity:** Don't rely on one provider. OpenRouter helps here by abstracting providers, but have a direct fallback to at least one provider (e.g., direct Anthropic API).
2. **Health check endpoint:** Periodically ping each model with a trivial prompt to detect outages before user traffic hits them.
3. **Timeout discipline:** Set aggressive timeouts (10-15s) -- a slow response is worse than a fallback.
4. **Stale cache serving:** If the LLM is down, serve cached responses even if slightly stale.

---

## 4. Structured Logging for Agents

### 4.1 What to Log per LLM Call

Every LLM call should produce a structured log entry with:

```python
import structlog

logger = structlog.get_logger("llm")

# After each LLM call:
logger.info(
    "llm_call",
    # Identity
    request_id=request_id,
    trace_id=trace_id,       # Correlates multi-step agent workflows
    span_id=span_id,         # Individual step within a trace

    # Call details
    model=model,
    provider="openrouter",
    operation="spam_classification",  # What the call is for

    # Tokens and cost
    input_tokens=usage.prompt_tokens,
    output_tokens=usage.completion_tokens,
    total_tokens=usage.total_tokens,
    cost_usd=calculated_cost,

    # Performance
    latency_ms=latency_ms,
    timeout_ms=timeout_setting,
    attempt=attempt_number,
    cached=was_cached,

    # Context
    chat_id=chat_id,
    user_id=user_id,
    message_id=message_id,

    # Result
    status="success",  # or "error", "timeout", "fallback"
    error_type=None,
    fallback_model=None,
)
```

### 4.2 Tracing Multi-Step Agent Workflows

For agent workflows that involve multiple LLM calls (e.g., classify -> analyze -> decide -> act):

```python
import uuid
from contextvars import ContextVar

# Trace context
current_trace_id: ContextVar[str] = ContextVar("trace_id")

class AgentTracer:
    def __init__(self):
        self.trace_id = str(uuid.uuid4())
        self.spans: list[dict] = []
        self.start_time = time.time()

    def span(self, operation: str):
        """Context manager for a single step in the agent workflow."""
        return TracerSpan(self, operation)

    def finish(self):
        total_cost = sum(s.get("cost_usd", 0) for s in self.spans)
        total_tokens = sum(s.get("total_tokens", 0) for s in self.spans)
        logger.info(
            "agent_trace_complete",
            trace_id=self.trace_id,
            total_spans=len(self.spans),
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            total_latency_ms=(time.time() - self.start_time) * 1000,
            operations=[s["operation"] for s in self.spans],
        )
```

### 4.3 Storing Logs for Analysis

Given our PostgreSQL stack, create an `llm_calls` table:

```sql
CREATE TABLE llm_calls (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID NOT NULL,
    span_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Call metadata
    model VARCHAR(100) NOT NULL,
    provider VARCHAR(50) DEFAULT 'openrouter',
    operation VARCHAR(100) NOT NULL,

    -- Tokens and cost
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd DECIMAL(10, 6),

    -- Performance
    latency_ms INTEGER,
    cached BOOLEAN DEFAULT FALSE,
    attempt INTEGER DEFAULT 1,
    status VARCHAR(20) NOT NULL,  -- success, error, timeout, fallback

    -- Context
    chat_id BIGINT,
    user_id BIGINT,

    -- Content (for debugging, consider privacy)
    input_hash VARCHAR(64),  -- SHA-256 of input, not the input itself
    error_message TEXT,

    -- Indexes
    INDEX idx_llm_calls_trace (trace_id),
    INDEX idx_llm_calls_created (created_at),
    INDEX idx_llm_calls_model (model),
    INDEX idx_llm_calls_operation (operation)
);
```

### 4.4 Integrating with structlog

Add a custom structlog processor for LLM metrics:

```python
import structlog

def add_llm_metrics(logger, method_name, event_dict):
    """Auto-calculate cost from token counts."""
    if event_dict.get("event") == "llm_call":
        model = event_dict.get("model", "")
        input_tokens = event_dict.get("input_tokens", 0)
        output_tokens = event_dict.get("output_tokens", 0)
        event_dict["cost_usd"] = calculate_cost(model, input_tokens, output_tokens)
    return event_dict

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        add_llm_metrics,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),  # or JSONRenderer for production
    ],
)
```

---

## 5. Budget Management

### 5.1 Per-Agent Budget Architecture

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class AgentBudget:
    agent_name: str
    daily_limit_usd: Decimal
    monthly_limit_usd: Decimal
    per_call_limit_usd: Decimal
    current_daily_spend: Decimal = Decimal("0")
    current_monthly_spend: Decimal = Decimal("0")

AGENT_BUDGETS = {
    "spam_detector": AgentBudget(
        agent_name="spam_detector",
        daily_limit_usd=Decimal("5.00"),
        monthly_limit_usd=Decimal("100.00"),
        per_call_limit_usd=Decimal("0.01"),
    ),
    "content_moderator": AgentBudget(
        agent_name="content_moderator",
        daily_limit_usd=Decimal("10.00"),
        monthly_limit_usd=Decimal("200.00"),
        per_call_limit_usd=Decimal("0.05"),
    ),
    "escalation_analyzer": AgentBudget(
        agent_name="escalation_analyzer",
        daily_limit_usd=Decimal("3.00"),
        monthly_limit_usd=Decimal("50.00"),
        per_call_limit_usd=Decimal("0.02"),
    ),
}
```

### 5.2 Budget Enforcement Middleware

```python
class BudgetMiddleware:
    async def check_budget(self, agent_name: str, estimated_cost: Decimal) -> bool:
        budget = await self.get_budget(agent_name)

        if budget.current_daily_spend + estimated_cost > budget.daily_limit_usd:
            logger.warning("budget_exceeded", agent=agent_name, period="daily",
                          spent=str(budget.current_daily_spend),
                          limit=str(budget.daily_limit_usd))
            return False

        if budget.current_monthly_spend + estimated_cost > budget.monthly_limit_usd:
            logger.warning("budget_exceeded", agent=agent_name, period="monthly")
            return False

        return True

    async def record_spend(self, agent_name: str, cost: Decimal):
        # Update PostgreSQL
        await self.repo.increment_spend(agent_name, cost)

        # Check alert thresholds (80%, 90%, 100%)
        budget = await self.get_budget(agent_name)
        pct = budget.current_daily_spend / budget.daily_limit_usd * 100
        if pct >= 80 and not budget.alert_sent_80:
            await self.send_alert(agent_name, pct)
```

### 5.3 Cost Tracking in PostgreSQL

```sql
CREATE TABLE agent_spend (
    id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(50) NOT NULL,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_calls INTEGER DEFAULT 0,
    total_input_tokens BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,
    total_cost_usd DECIMAL(10, 6) DEFAULT 0,
    UNIQUE(agent_name, date)
);

-- Daily cost report query
SELECT
    agent_name,
    date,
    total_calls,
    total_cost_usd,
    total_cost_usd / NULLIF(total_calls, 0) AS avg_cost_per_call
FROM agent_spend
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY date DESC, total_cost_usd DESC;
```

### 5.4 Alerting

Integrate with existing Telegram admin notifications:

- **80% of daily budget:** Warning message to admin chat
- **100% of daily budget:** Critical alert + agent switches to degraded mode
- **Cost spike detection:** If hourly cost > 3x the average hourly cost, alert immediately
- **Monthly projection:** If linear projection of current spend exceeds monthly budget by day 15, alert

### 5.5 Token Usage Forecasting

Simple approach: store daily token counts, compute 7-day moving average, project forward.

```python
async def forecast_monthly_cost(agent_name: str) -> Decimal:
    # Get last 7 days of spend
    recent = await repo.get_recent_spend(agent_name, days=7)
    avg_daily = sum(r.total_cost_usd for r in recent) / len(recent)
    days_remaining = days_in_month - current_day
    projected = sum(r.total_cost_usd for r in month_so_far) + avg_daily * days_remaining
    return projected
```

---

## 6. OpenRouter-Specific

### 6.1 OpenRouter's Built-In Features

**Provider Routing:**
- OpenRouter automatically routes to the cheapest available provider for each model
- Supports provider preferences via `provider.order` and `provider.allow` / `provider.deny`
- Can prefer providers by latency, price, or throughput

**Fallback Configuration:**
- Set `route: "fallback"` in request to automatically try alternative providers
- Use `models` array to specify fallback model chain:
  ```json
  {
    "model": "google/gemini-2.0-flash",
    "route": "fallback",
    "models": [
      "google/gemini-2.0-flash",
      "google/gemini-1.5-flash",
      "meta-llama/llama-3.1-8b-instruct"
    ]
  }
  ```

**Rate Limits:**
- Free tier: 20 requests/min, 200 requests/day
- Paid: Rate limits depend on credits; generally 100+ requests/min
- Headers returned: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Monitor via response headers and handle 429 status codes

**Analytics:**
- OpenRouter dashboard shows per-model usage, costs, and request history
- API endpoint `/api/v1/auth/key` returns current credit balance
- No built-in alerting or per-agent breakdown (need external tooling)

### 6.2 OpenRouter Cost Tracking

```python
# OpenRouter returns cost in the response
response = await client.chat.completions.create(...)
# Access via response headers or usage field
# x-openrouter-cost header contains the cost in USD

# Parse from response
cost = getattr(response, 'usage', {}).get('cost', None)
# Or from headers if using raw HTTP
cost = float(response.headers.get('x-openrouter-cost', 0))
```

### 6.3 OpenRouter Limitations

- **No built-in caching:** Must implement externally
- **No budget caps:** Must implement in your application
- **No per-key analytics API:** Dashboard only, limited programmatic access
- **Provider outages:** OpenRouter handles provider-level failover, but if OpenRouter itself is down, you need a direct fallback

### 6.4 Recommendation: Direct API Fallback

Keep a direct Anthropic or Google API key as emergency fallback:

```python
async def call_with_openrouter_fallback(prompt, model):
    try:
        return await openrouter_call(prompt, model)
    except (ConnectionError, TimeoutError):
        # OpenRouter itself is down, use direct API
        if "gemini" in model:
            return await direct_google_call(prompt)
        elif "claude" in model:
            return await direct_anthropic_call(prompt)
```

---

## 7. Recommendations for Our Stack

### Priority 1: Quick Wins (1-2 days)

1. **Add LLM call logging table** to PostgreSQL (see Section 4.3 schema)
   - Track every call: model, tokens, cost, latency, operation, status
   - Query for daily cost reports

2. **Implement exact-match caching** in PostgreSQL
   - Hash prompt + model + temperature -> cache response
   - 1-hour TTL for moderation calls
   - Expected savings: 20-30%

3. **Add budget enforcement** per agent (Section 5.2)
   - Daily caps with Telegram alerts at 80%/100%
   - Graceful degradation to rule-based when budget exceeded

4. **Set `max_tokens`** on all LLM calls to prevent runaway costs

### Priority 2: Reliability (3-5 days)

5. **Implement retry + fallback chain** (Section 3.1)
   - Primary: Gemini Flash -> Gemini 1.5 Flash -> Llama 3.1 8B
   - Use OpenRouter's `route: "fallback"` for provider-level failover

6. **Add circuit breaker** per model/provider (Section 3.2)
   - 5 failures = open circuit for 60 seconds
   - Prevents hammering a down provider

7. **Graceful degradation** to rule-based moderation when AI is unavailable
   - Maintain a keyword/regex blocklist as baseline
   - Always functional, no LLM dependency

### Priority 3: Observability Platform (1 week)

8. **Deploy Langfuse self-hosted** via Docker
   - Add to `docker-compose.dev.yaml`
   - Minimal resource usage (just needs PostgreSQL, which we already have)
   - Full tracing, cost dashboards, prompt versioning
   - Instrument PydanticAI calls with `@observe` decorator

   Alternatively, start with **Helicone free tier** (100k requests/mo) for zero-code-change proxy approach -- just change the OpenRouter base URL.

### Priority 4: Advanced (2+ weeks)

9. **Model routing by task complexity** (Section 2.2)
   - Classify message complexity before choosing model
   - Expected savings: 50-70% on LLM costs

10. **Semantic caching** with pgvector (only if exact-match caching savings are insufficient)

11. **Cost anomaly detection** -- alert if hourly spend > 3x average

### Architecture Diagram

```
Telegram Message
       |
       v
+------------------+
| Rate Limiter     |  <-- Per-chat, per-minute limits
+------------------+
       |
       v
+------------------+
| Budget Check     |  <-- Per-agent daily/monthly caps
+------------------+
       |
       v
+------------------+
| Cache Lookup     |  <-- Exact match (PostgreSQL)
+------------------+
       |  (miss)
       v
+------------------+
| Circuit Breaker  |  <-- Is the provider healthy?
+------------------+
       |
       v
+------------------+     +------------------+
| OpenRouter API   | --> | Fallback Chain   |
| (primary model)  |     | (retry + models) |
+------------------+     +------------------+
       |
       v
+------------------+
| Log + Track Cost |  <-- structlog + PostgreSQL
+------------------+
       |
       v
+------------------+
| Langfuse/        |  <-- Optional: traces, dashboards
| Helicone         |
+------------------+
```

### Estimated Monthly Costs

Assuming 10k messages/day processed by AI agents:

| Component | Without Optimization | With Optimization |
|---|---|---|
| LLM API calls | $300-600/mo | $50-100/mo |
| Langfuse (self-hosted) | $0 | $0 |
| PostgreSQL (existing) | $0 | $0 |
| **Total observability overhead** | -- | **~$0** (self-hosted) |

### Key Links

- Langfuse: https://langfuse.com/docs
- Langfuse Python SDK: https://langfuse.com/docs/sdk/python
- Helicone: https://docs.helicone.ai
- Phoenix (Arize): https://github.com/Arize-AI/phoenix
- Portkey: https://portkey.ai/docs
- OpenRouter API docs: https://openrouter.ai/docs
- OpenRouter provider routing: https://openrouter.ai/docs/features/provider-routing
- PydanticAI observability: https://ai.pydantic.dev/logfire/
- structlog: https://www.structlog.org
