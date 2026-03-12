# Autonomous Content Generation and Distribution Systems

Research document for building an autonomous Telegram channel content pipeline.

**Scope:** Content discovery, LLM-based generation, multilingual publishing, human-in-the-loop review, and adaptive learning from admin feedback.

**Date:** March 2026 (based on knowledge through mid-2025; verify links and pricing)

---

## 1. Content Automation Platforms

### 1.1 General-Purpose Automation

| Platform | AI Features | Telegram Support | Self-Hosted | Pricing |
|----------|------------|-----------------|-------------|---------|
| **n8n** | Built-in AI nodes (OpenAI, Anthropic, Ollama), LangChain integration, vector stores | Native Telegram node (Bot API) | Yes (Docker) | Free self-hosted, cloud from $20/mo |
| **Make.com** | AI modules, OpenAI/Claude integrations, JSON/text parsing | Telegram module (send, watch, edit) | No | Free tier (1000 ops), from $9/mo |
| **Zapier** | AI Actions, built-in AI text generation, "AI by Zapier" step | Telegram Zap integration | No | Free tier limited, from $19.99/mo |
| **Activepieces** | AI pieces, open-source alternative to Zapier | Telegram piece available | Yes | Free self-hosted |

### 1.2 Recommendations for This Project

**n8n is the strongest candidate** for orchestration because:
- Fully self-hosted (Docker) -- no vendor lock-in, no per-operation costs
- Native AI agent nodes with tool-calling support (LangChain under the hood)
- Built-in Telegram Bot API node for sending/editing/deleting messages
- Webhook triggers for receiving admin approval callbacks
- Cron/schedule triggers for timed publishing
- HTTP Request node for RSS fetching, API calls
- Code node (JavaScript/Python) for custom logic
- Credential management for API keys
- Visual workflow debugging

However, for maximum control and integration with the existing bot codebase, **a custom Python pipeline** (using asyncio, aiohttp, APScheduler or aiocron) is likely more maintainable. n8n can be used as a supplementary visual orchestrator for non-developers.

### 1.3 Social Media Management Platforms

| Platform | AI Content Features | Multi-Channel | API Access |
|----------|-------------------|---------------|------------|
| **Buffer** | AI Assistant for post generation, hashtag suggestions | Yes (no Telegram) | REST API |
| **Hootsuite** | OwlyWriter AI, content suggestions, best-time-to-post | Yes (no native Telegram) | Limited API |
| **Sprout Social** | AI Assist, sentiment analysis, suggested replies | Yes (no Telegram) | API available |
| **Later** | AI caption writer, visual planning | Instagram-focused | API available |

**Note:** None of the major social media management platforms natively support Telegram channels. Telegram publishing requires custom integration via Bot API or client API.

---

## 2. AI Content Generation at Scale

### 2.1 How Organizations Use LLMs for Content

**Media Companies:**
- Associated Press, Bloomberg: Automated financial/sports reporting from structured data
- BuzzFeed (before downsizing): Used OpenAI for quizzes, listicles, personalized content
- CNET, Bankrate: AI-generated articles with human editorial review (faced backlash for factual errors)

**Marketing Agencies:**
- Use LLMs for first-draft generation, then human editing
- Multi-variant A/B testing of headlines and copy
- SEO content generation with programmatic keyword targeting

**Content Operations Teams:**
- LLM generates draft from source material (article, data, brief)
- Human editor reviews, fact-checks, adjusts tone
- Content goes through approval workflow before publishing

### 2.2 Quality Control and Guardrails

| Technique | Description | Implementation |
|-----------|-------------|----------------|
| **System prompt engineering** | Detailed persona, style guide, constraints | Include tone, length, formatting rules, prohibited content |
| **Few-shot examples** | Provide 3-5 examples of ideal output | Store approved posts as reference in prompt |
| **Temperature control** | Lower temperature (0.3-0.5) for factual content | Higher (0.7-0.9) for creative posts |
| **Output validation** | Check length, format, language, prohibited words | Regex, language detection (langdetect/fasttext), profanity filters |
| **Diversity enforcement** | Track recent outputs, prevent repetition | Maintain rolling window of recent topics/phrases, include in negative prompt |
| **Factual grounding** | Generate only from provided source material | "Only use information from the following article. Do not add facts." |
| **Human-in-the-loop** | Admin review before publishing | Inline keyboard with approve/edit/reject buttons |
| **Feedback loop** | Learn from admin edits and rejections | Store approve/reject/edit history, fine-tune prompts or use as few-shot examples |

### 2.3 Avoiding Repetitive/Low-Quality Output

1. **Topic deduplication**: Before generating, check semantic similarity (embeddings) against recent posts. Skip if cosine similarity > 0.85.
2. **Style variation**: Rotate between prompt templates (informative, conversational, Q&A, list-based).
3. **Source diversity**: Pull from multiple RSS feeds, APIs, and social sources to avoid echo-chamber content.
4. **Freshness scoring**: Prioritize recent, trending content. Deprioritize topics already covered.
5. **Negative examples**: Include rejected posts in the prompt as "do NOT write like this."
6. **Post-generation checks**: Language detection, minimum information density, readability score.

### 2.4 Recommended LLM Strategy

For this project's content generation pipeline:

| Task | Recommended Model | Reasoning |
|------|------------------|-----------|
| Content screening/relevance | gemini-2.0-flash, gpt-4o-mini | Fast, cheap, good at classification |
| Post generation (Russian) | claude-sonnet-4, gpt-4o | Strong Russian language quality |
| Post generation (Czech) | claude-sonnet-4, gpt-4o | Decent Czech; verify with native speaker |
| Post generation (English) | Any frontier model | All perform well in English |
| Summarization | gemini-2.0-flash, gpt-4o-mini | Fast, cost-effective for extractive tasks |
| Translation | gpt-4o, claude-sonnet-4 | Best translation quality at scale |

**Cost optimization**: Use cheaper models (flash/mini) for screening and routing, frontier models only for final generation.

---

## 3. Content Discovery and Curation

### 3.1 RSS and Feed-Based Discovery

| Tool/Library | Type | Features |
|-------------|------|----------|
| **feedparser** (Python) | Library | Parse RSS/Atom feeds, robust error handling |
| **aiohttp + feedparser** | Custom | Async fetching of multiple feeds in parallel |
| **Feedly** | SaaS + API | AI-powered topic clustering, deduplication, keyword alerts. API from Pro+ ($12/mo) |
| **Inoreader** | SaaS + API | Rules engine, keyword monitoring, API access |

### 3.2 News APIs

| API | Coverage | Languages | Free Tier | Notes |
|-----|----------|-----------|-----------|-------|
| **NewsAPI.org** | 150K+ sources | Multi-language | 100 req/day (dev only) | No production use on free tier; paid from $449/mo |
| **GNews API** | Google News | Multi-language | 100 req/day | Simpler, cheaper alternative |
| **Bing News Search** (Azure) | Broad | Multi-language | 1000 req/mo free | Part of Azure Cognitive Services |
| **Google News RSS** | Broad | Multi-language | Free | No official API, but RSS feeds work: `news.google.com/rss/search?q=...&hl=cs&gl=CZ` |
| **Mediastack** | 7500+ sources | Multi-language | 500 req/mo free | REST API, good for news aggregation |
| **NewsCatcher** | 60K+ sources | Multi-language | Trial available | NLP-enriched, topic clustering |
| **Event Registry** | Global | Multi-language | Free tier available | Event-centric, concept-based search |

### 3.3 Social Listening and Content Discovery

| Tool | Type | Use Case |
|------|------|----------|
| **Brandwatch** | Enterprise SaaS | Social listening, trend detection, sentiment analysis |
| **Mention** | SaaS | Brand monitoring, keyword alerts across web/social |
| **Google Alerts** | Free | Email alerts for keywords (can be parsed programmatically) |
| **Reddit API** | API | Monitor subreddits (r/czech, r/prague, etc.) |
| **Telegram Channel Monitoring** | Custom | Use Telethon to monitor source channels |
| **Twitter/X API** | API | Keyword/hashtag monitoring (expensive since 2023) |
| **Hacker News API** | Free API | Tech content discovery |

### 3.4 Recommended Discovery Stack for This Project

```
Priority 1 (Free/Low-cost):
  - RSS feeds (feedparser + aiohttp) -- curated list of Czech/Russian news sources
  - Google News RSS -- keyword-based, language-filtered
  - Telegram channel monitoring (Telethon) -- monitor source channels directly
  - Reddit API -- relevant subreddits

Priority 2 (Paid but valuable):
  - GNews API or Mediastack -- structured news search
  - Feedly API -- AI-powered curation

Priority 3 (Future):
  - Custom web scrapers for specific high-value sources
  - Social listening integration
```

### 3.5 Content Discovery Pipeline Architecture

```
[RSS Feeds] ──┐
[News APIs] ──┤
[Telegram]  ──┼──> Deduplication ──> Relevance Scoring (LLM) ──> Content Queue
[Reddit]    ──┤         |                    |
[Scrapers]  ──┘    (URL hash +         (0-1 score +
                   title embedding)     topic tags)
```

---

## 4. Telegram-Specific Automation

### 4.1 Bot API vs Client API

| Feature | Bot API (aiogram) | Client API (Telethon/Pyrogram) |
|---------|-------------------|-------------------------------|
| **Auth** | Bot token | Phone number + 2FA |
| **Channel posting** | Bot must be channel admin | Can post as user/channel |
| **Read channel history** | Only own messages | Full history access |
| **Monitor other channels** | No | Yes -- key advantage |
| **User search** | No | Yes |
| **Rate limits** | ~30 msg/sec to different chats; 20 msg/min to same group | Stricter, MTProto flood waits |
| **TOS risk** | None | Moderate (automation on user accounts) |
| **Best for** | Publishing to own channels | Content discovery from source channels |

### 4.2 Pyrogram vs Telethon

| Aspect | Pyrogram | Telethon |
|--------|----------|----------|
| **Async** | Native async | Native async |
| **Python version** | 3.7+ | 3.5+ |
| **API coverage** | Complete MTProto | Complete MTProto |
| **Documentation** | Good, modern | Excellent, extensive |
| **Community** | Active | Larger community |
| **Maintenance** | Pyrogram maintained as pyrofork by community | Actively maintained |
| **Session storage** | SQLite, MongoDB, string | SQLite, string |
| **Ease of use** | Slightly easier syntax | More flexible |

**Recommendation:** Use **Telethon** for content discovery (monitoring source channels) and **aiogram** (Bot API) for publishing to your own channels. This hybrid approach is common and respects Telegram's intended use patterns.

### 4.3 Telegram Rate Limits (Bot API)

These are approximate and can change:

| Limit | Value |
|-------|-------|
| Messages to same chat | ~20 per minute |
| Messages to different chats | ~30 per second |
| Bulk notifications | ~30 messages/second, may get 429 errors |
| Inline query results | 50 results per query |
| File upload | 50 MB (bot API), 2 GB (client API) |
| Message length | 4096 characters |
| Caption length | 1024 characters |
| Callback query answer | Must respond within ~10 seconds |
| getUpdates long polling | 30 second timeout recommended |

**Anti-flood best practices:**
- Implement exponential backoff on 429 (Too Many Requests) errors
- Parse `retry_after` field from Telegram's error response
- Queue outgoing messages with rate limiter (e.g., `aiolimiter`)
- For scheduled publishing, space posts at least 3-5 minutes apart
- For bulk operations, use `asyncio.Semaphore` to limit concurrency

### 4.4 Telegram Channel Management Tools

| Tool | Type | Features |
|------|------|----------|
| **TGStat** (tgstat.ru) | Analytics SaaS | Channel analytics, growth tracking, post performance, audience overlap |
| **Telemetr** (telemetr.me) | Analytics SaaS | Similar to TGStat, popular in Russian-speaking market |
| **Combot** | Bot + Dashboard | Group analytics, anti-spam, moderation (less for channels) |
| **Controller Bot** (@ControllerBot) | Telegram bot | Post scheduling, reactions, delayed posting, inline buttons |
| **PostBot** | Telegram bot | Simple scheduled posting |
| **Crosser Bot** | Telegram bot | Cross-posting between channels |

### 4.5 Recommended Architecture for This Project

```
Content Discovery (Telethon client API):
  - Monitor curated source channels
  - Fetch from RSS/News APIs

Content Processing (Python async pipeline):
  - Deduplication (URL hash + embedding similarity)
  - Relevance scoring (LLM: gemini-flash)
  - Content generation (LLM: claude-sonnet/gpt-4o)
  - Multi-language generation

Human Review (aiogram Bot API):
  - Send draft to admin review chat
  - Inline keyboard: Approve / Edit / Reject / Schedule
  - Edit flow: admin replies with corrected text
  - Learn from decisions (store in DB)

Publishing (aiogram Bot API):
  - Scheduled posting via APScheduler or aiocron
  - Rate-limited message sending
  - Post-publish analytics tracking
```

---

## 5. Multilingual Content Generation

### 5.1 Translation vs Native Generation

| Approach | Pros | Cons |
|----------|------|------|
| **Generate in English, translate** | Consistent base content, easier QA | Translation artifacts, unnatural phrasing |
| **Generate natively per language** | Most natural output, culturally adapted | May diverge between languages, harder to QA |
| **Generate in primary language, adapt** | Balance of consistency and naturalness | Still some adaptation artifacts |

**Recommendation for this project:** Generate natively in each target language from the source material. LLMs are strong enough in Russian and English to produce natural text. For Czech, generate natively but consider a review step since LLM Czech quality is lower than Russian/English.

### 5.2 LLM Performance by Language

| Language | Best Models | Quality Notes |
|----------|-------------|---------------|
| **English** | All frontier models | Excellent across the board |
| **Russian** | GPT-4o, Claude Sonnet/Opus, Gemini Pro | Very strong. Russian is well-represented in training data |
| **Czech** | GPT-4o, Claude Sonnet, Gemini Pro | Good but not perfect. Common issues: incorrect declension, calques from English, awkward word order. Review recommended |

### 5.3 Best Practices for Multilingual Generation

1. **Language-specific system prompts**: Separate, carefully crafted prompts per language. Include style notes specific to that language's conventions.

2. **Native speaker review**: Especially for Czech, have a native speaker review the first ~50 posts to identify systematic issues, then encode corrections into the prompt.

3. **Terminology glossaries**: Maintain a glossary of domain-specific terms (e.g., Czech bureaucracy terms, immigration terminology) and include in the prompt.

4. **Cultural adaptation, not just translation**: A post about "tax season" for a US audience needs completely different framing for Czech readers. Generate from the underlying facts, not from another language's post.

5. **Language detection validation**: After generation, run `langdetect` or `fasttext` to verify the output is in the correct language. LLMs occasionally slip into the wrong language.

6. **Length considerations**: Russian text is typically 10-20% longer than English for the same content. Czech is similar to English in length. Design message templates with this in mind.

7. **Emoji and formatting**: Telegram supports rich formatting (bold, italic, links, emoji). Different audiences may prefer different emoji density. Russian-speaking Telegram tends to use more emoji than Czech-speaking channels.

### 5.4 Implementation Pattern

```python
# Pseudocode for multilingual post generation

LANGUAGE_CONFIGS = {
    "ru": {
        "model": "openrouter/anthropic/claude-sonnet-4",
        "system_prompt": "Ты -- редактор Telegram-канала для русскоязычных в Чехии...",
        "max_length": 3500,
        "glossary": load_glossary("ru"),
    },
    "cs": {
        "model": "openrouter/openai/gpt-4o",
        "system_prompt": "Jsi redaktor Telegram kanalu pro ceskou komunitu...",
        "max_length": 3500,
        "glossary": load_glossary("cs"),
        "review_required": True,  # Flag for mandatory human review
    },
    "en": {
        "model": "openrouter/anthropic/claude-sonnet-4",
        "system_prompt": "You are an editor for a Telegram channel...",
        "max_length": 3500,
        "glossary": load_glossary("en"),
    },
}

async def generate_multilingual_posts(source_content: str, languages: list[str]):
    posts = {}
    for lang in languages:
        config = LANGUAGE_CONFIGS[lang]
        post = await generate_post(
            model=config["model"],
            system_prompt=config["system_prompt"],
            source=source_content,
            glossary=config["glossary"],
            max_length=config["max_length"],
        )
        # Validate language
        detected = detect_language(post.text)
        if detected != lang:
            logger.warning(f"Language mismatch: expected {lang}, got {detected}")
            post = await regenerate_with_language_emphasis(...)
        posts[lang] = post
    return posts
```

---

## 6. Learning from Admin Feedback

### 6.1 Feedback Loop Architecture

```
Admin Action          Data Captured              Usage
─────────────────────────────────────────────────────────
Approve               source + generated post    Positive example for few-shot
Reject                source + generated post    Negative example, analyze why
Edit then approve     source + original + edit   Edit diff = quality signal
Schedule change       original time + new time   Learn optimal posting times
Ignore (no action)    source + generated post    Likely low-relevance source
```

### 6.2 Adaptive Prompt Engineering

Rather than fine-tuning (expensive, complex), use **dynamic few-shot selection**:

1. Store all admin decisions in a database table: `(source_content, generated_post, admin_action, admin_edit, language, timestamp, topic_tags)`
2. When generating a new post, retrieve the 3-5 most relevant approved posts (by topic similarity via embeddings) as few-shot examples
3. Also retrieve 1-2 rejected posts as negative examples
4. Include in the generation prompt: "Here are examples of posts our editors approved: ... Here are posts they rejected: ..."

### 6.3 Source Quality Learning

Track approve/reject rates per source (RSS feed, channel, API):

```sql
-- Source quality scoring
SELECT
    source_id,
    source_name,
    COUNT(*) as total,
    SUM(CASE WHEN action = 'approve' THEN 1 ELSE 0 END) as approved,
    ROUND(AVG(CASE WHEN action = 'approve' THEN 1.0 ELSE 0.0 END), 2) as approval_rate
FROM content_decisions
GROUP BY source_id, source_name
ORDER BY approval_rate DESC;
```

Use approval rates to weight source priority in the discovery pipeline. Sources below 20% approval rate get flagged for removal.

---

## 7. Practical Recommendations for Implementation

### 7.1 Technology Choices

| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| Orchestration | Custom Python async pipeline | Integrates with existing bot codebase |
| Content discovery | feedparser + aiohttp + Telethon | Free, flexible, covers RSS + Telegram sources |
| News API | GNews API or Google News RSS | Cost-effective, good language support |
| LLM provider | OpenRouter (already in project) | Multi-model access, single API |
| Screening model | gemini-2.0-flash | Fast, cheap, good at classification |
| Generation model | claude-sonnet-4 / gpt-4o | Best multilingual quality |
| Scheduling | APScheduler or aiocron | Async-compatible, cron expressions |
| Rate limiting | aiolimiter | Token bucket algorithm for Telegram API |
| Deduplication | URL hashing + sentence-transformers embeddings | Catches both exact and semantic duplicates |
| Language detection | fasttext (lid.176.bin) or langdetect | Fast, accurate, supports Czech/Russian |
| Admin review | aiogram inline keyboards | Already in the bot stack |
| Feedback storage | PostgreSQL (existing) | New tables for content decisions |

### 7.2 New Database Tables Needed

```
content_sources       -- RSS feeds, channels, APIs to monitor
content_items         -- Discovered raw content items
content_posts         -- Generated posts (per language)
content_decisions     -- Admin approve/reject/edit actions
content_schedule      -- Publishing schedule
content_glossaries    -- Term glossaries per language
```

### 7.3 Phased Implementation

**Phase 1 -- MVP (1-2 weeks):**
- RSS feed fetching (3-5 curated sources)
- Basic deduplication (URL hash)
- LLM relevance screening
- Single-language post generation (Russian)
- Admin review via inline keyboard (approve/reject)
- Manual publish on approve

**Phase 2 -- Multi-language + Scheduling (1-2 weeks):**
- Add Czech and English generation
- Scheduled publishing (APScheduler)
- Basic feedback storage
- Source quality tracking

**Phase 3 -- Intelligence (2-3 weeks):**
- Telegram channel monitoring via Telethon
- Semantic deduplication (embeddings)
- Dynamic few-shot from admin feedback
- Posting time optimization
- Analytics dashboard in webapp

**Phase 4 -- Advanced (ongoing):**
- News API integration
- Social listening
- A/B testing of post formats
- Automated source discovery
- Full webapp management interface

### 7.4 Key Links and Resources

**Libraries:**
- feedparser: https://feedparser.readthedocs.io/
- aiolimiter: https://github.com/mjpieters/aiolimiter
- APScheduler: https://apscheduler.readthedocs.io/
- sentence-transformers: https://www.sbert.net/
- langdetect: https://github.com/Mimino666/langdetect
- fasttext language identification: https://fasttext.cc/docs/en/language-identification.html
- Telethon: https://docs.telethon.dev/
- Pyrogram (pyrofork): https://github.com/Mayuri-Chan/pyrofork

**APIs:**
- Telegram Bot API: https://core.telegram.org/bots/api
- OpenRouter: https://openrouter.ai/docs
- GNews API: https://gnews.io/
- NewsAPI: https://newsapi.org/ (expensive for production)
- Mediastack: https://mediastack.com/
- Google News RSS: `https://news.google.com/rss/search?q=QUERY&hl=LANG&gl=COUNTRY`

**Analytics:**
- TGStat: https://tgstat.ru/
- Telemetr: https://telemetr.me/

**Automation Platforms (for reference):**
- n8n: https://n8n.io/
- Make.com: https://make.com/
- Activepieces: https://www.activepieces.com/
