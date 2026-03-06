# Telegram Ecosystem Research: Advanced Automation and Community Management

> Research compiled March 2026. Based on knowledge through mid-2025; items marked [VERIFY] should be checked against latest docs.

---

## Table of Contents

1. [Telegram Client API: Pyrogram vs Telethon](#1-telegram-client-api-pyrogram-vs-telethon)
2. [Telegram Bot API Advanced Features](#2-telegram-bot-api-advanced-features)
3. [Large-Scale Community Management](#3-large-scale-community-management)
4. [Advertising and Monetization](#4-advertising-and-monetization)
5. [Anti-Abuse and Rate Limits](#5-anti-abuse-and-rate-limits)
6. [Telegram Analytics](#6-telegram-analytics)
7. [Legal and Compliance (EU/Czech Republic)](#7-legal-and-compliance-euczech-republic)
8. [Architecture Recommendations for Our Project](#8-architecture-recommendations-for-our-project)

---

## 1. Telegram Client API: Pyrogram vs Telethon

### Why Client API (MTProto) Over Bot API

The Bot API is an HTTP wrapper around Telegram's native MTProto protocol. The Client API (also called "userbot" API) gives access to everything a regular Telegram user can do, plus bot-specific methods. Key capabilities the Bot API lacks:

| Capability | Bot API | Client API |
|---|---|---|
| Read full message history | No (only messages sent to bot) | Yes |
| Search messages in chats | No | Yes |
| Get full user info (phone, last seen) | No | Yes (with privacy settings) |
| Join/leave chats programmatically | No | Yes |
| Manage channel posts as user | No | Yes |
| Access user's contact list | No | Yes |
| Forward messages between chats | Limited | Full control |
| Get chat member list (full) | Limited (getAdmins only in large groups) | Yes |
| Manage Telegram Ads | No | Yes (via TL schema) |
| View stories | No [VERIFY] | Yes |
| React to messages (custom emoji) | Limited | Full |
| Download any file up to 4GB | 20MB limit (Bot API), 2GB via local server | 4GB native |
| Scrape public channels | No | Yes |
| Get message view counts | No | Yes |
| Pin messages silently | Yes | Yes + more options |

### Pyrogram

- **Repository**: https://github.com/pyrogram/pyrogram
- **Current state (as of early 2025)**: Pyrogram v2.x is the main branch. Maintained by Dan (the original author), though development pace slowed in 2023-2024. Community forks exist (e.g., `pyrogram` on PyPI vs forks like `pyrofork`).
- **Async support**: Full async/await since v2.0
- **Python support**: 3.8+ (3.12 works fine)
- **Documentation**: https://docs.pyrogram.org/ -- Good quality, well-structured, with many examples
- **Key strengths**:
  - Pythonic, clean API design
  - Built-in session management (SQLite-based)
  - Automatic MTProto layer updates (usually)
  - Easy to use for both userbots and bots
  - Decorators-based event handling (similar to Flask)
  - Smart file handling with automatic chunked upload/download
- **Key weaknesses**:
  - Slower update cycle for new Telegram features [VERIFY current status]
  - Smaller maintainer team
  - Some community fragmentation (forks)
- **Installation**: `pip install pyrogram tgcrypto` (tgcrypto for speed)

**Example -- reading chat history:**
```python
from pyrogram import Client

app = Client("my_account", api_id=API_ID, api_hash=API_HASH)

async with app:
    async for message in app.get_chat_history("target_chat", limit=100):
        print(message.text)
```

### Telethon

- **Repository**: https://github.com/LonamiWebs/Telethon
- **Current state**: Telethon v1.x is stable and widely used. Telethon v2.0 was in alpha/beta through 2024-2025 with major API redesign. [VERIFY if v2.0 is stable yet]
- **Async support**: Full async since v1.0 (was one of the first async Telegram libs)
- **Python support**: 3.8+ (3.12 works)
- **Documentation**: https://docs.telethon.dev/ -- Comprehensive but can be dense; excellent for advanced use
- **Key strengths**:
  - Most mature MTProto library for Python
  - Excellent raw API access (you can call any TL method directly)
  - Better maintained long-term, responsive maintainer (Lonami)
  - Large community, more StackOverflow answers
  - Better for advanced/low-level operations
  - Session string support (easy to deploy in containers)
- **Key weaknesses**:
  - v2.0 migration may break existing code significantly
  - Raw API calls require understanding TL schema
  - Slightly steeper learning curve than Pyrogram
- **Installation**: `pip install telethon`

**Example -- reading chat history:**
```python
from telethon import TelegramClient

client = TelegramClient('session', api_id, api_hash)

async with client:
    async for message in client.iter_messages('target_chat', limit=100):
        print(message.text)
```

### Recommendation for Our Project

**Use Telethon** for the Client API layer, for these reasons:
1. More reliable long-term maintenance
2. Better raw API access (needed for ads management, analytics)
3. Session string support simplifies Docker deployment
4. Our team already uses async Python (aiogram), so the learning curve is minimal
5. Can coexist with aiogram -- aiogram handles Bot API, Telethon handles Client API

**Architecture pattern**: Run the bot via aiogram (Bot API) for all standard moderation. Use a separate Telethon client (userbot) for privileged operations: analytics scraping, message history export, ads management, cross-chat user tracking.

### Key Resources

- Pyrogram docs: https://docs.pyrogram.org/
- Telethon docs: https://docs.telethon.dev/
- Telegram MTProto API docs: https://core.telegram.org/api
- TL schema reference: https://core.telegram.org/schema
- Getting api_id/api_hash: https://my.telegram.org/apps

---

## 2. Telegram Bot API Advanced Features

### Latest Bot API Features (2024-2025) [VERIFY for 2026 additions]

#### Mini Apps (WebApps)
- Full-screen web applications inside Telegram
- Access to user's theme, viewport, biometric auth
- Can send data back to bot, trigger payments
- **Our project already uses this** for the admin panel
- Key updates:
  - `web_app_data` field in messages
  - Full-screen mode support
  - Accelerometer, gyroscope, device orientation APIs [VERIFY]
  - Cloud storage for Mini Apps (key-value, per-user)
  - Secondary button support
  - Bottom bar customization
  - `requestWriteAccess` -- Mini App can request permission to message user
- **Docs**: https://core.telegram.org/bots/webapps

#### Payments 2.0
- Native payment integration (Stripe, etc.)
- Stars (Telegram's virtual currency) -- users can pay with Stars
- Bots can accept Stars for digital goods and services
- Subscription model support [VERIFY]
- `sendInvoice`, `createInvoiceLink` methods
- **Opportunity**: Charge advertisers via Telegram Stars or traditional payment
- **Docs**: https://core.telegram.org/bots/payments

#### Topics/Forums
- Groups can be organized into topics (like Discord channels)
- Bots can create, manage, close, reopen topics
- Each topic has its own message thread
- `createForumTopic`, `editForumTopic`, `closeForumTopic`, etc.
- **Use case**: Organize educational chat by subject (Czech language, visa, housing, etc.)

#### Chat Boosts
- Users can boost chats to unlock features
- Bots can check boost status via `getChatBoosts`
- Boosted chats get: custom emoji in names, custom backgrounds, more
- **Marginal utility for us** but could gamify community engagement

#### Business Features
- Bots can manage business accounts
- Handle business messages, set away messages
- Manage business hours, location
- **Could be relevant** if we build advertiser-facing bot interactions

#### Reactions and Custom Emoji
- Bots can set message reactions
- Custom emoji packs can be created by bots
- `setMessageReaction` method
- **Use case**: Auto-react to approved content, mark reviewed messages

#### Inline Mode Enhancements
- `SwitchInlineQueryChosenChat` -- direct user to specific chat for inline query
- Cached inline results with longer TTL
- Web App buttons in inline results

#### Other Notable Features
- `copyMessages` (bulk copy)
- `forwardMessages` (bulk forward)
- Message effects (animations on send)
- Birthdate field in user objects
- `ChatFullInfo` with more metadata
- `getStarTransactions` for payment tracking
- Giveaway support (`createChatSubscriptionInviteLink`)
- Paid media support (photos/videos behind Star paywall)

### Bot API Local Server

For our scale, consider running a local Bot API server:
- Removes 20MB file upload limit (up to 2GB)
- Faster response times (no Telegram cloud middleman for file ops)
- Access to `file_path` as local filesystem path
- **Setup**: https://github.com/tdlib/telegram-bot-api
- **Docker image**: `ghcr.io/aiogram/telegram-bot-api`

---

## 3. Large-Scale Community Management

### How Large Channels Operate (100k+ subscribers)

#### Team Structure
- **Owner/founder** -- strategic decisions, advertiser relations
- **Content manager(s)** -- post scheduling, content creation
- **Moderators** (3-10) -- message review, user management
- **Ad manager** -- advertiser intake, scheduling, analytics reporting

#### Common Tools and Patterns

1. **Post Scheduling**: Telegram's built-in scheduled messages, or tools like Combot, Controllerbot
2. **Cross-posting**: Content goes to main channel, discussion group auto-linked
3. **Admin bots**: Custom or off-the-shelf (Combot, Rose, GroupHelp)
4. **CRM for advertisers**: Usually Google Sheets or Notion, sometimes custom
5. **Analytics**: TGStat, Telemetr, Popsters, custom dashboards

#### Automation Patterns for Large Communities

**Content Pipeline:**
```
Content creation -> Review queue -> Scheduled publish -> Cross-post to groups -> Analytics
```

**Moderation Pipeline:**
```
New message -> AI filter (spam/toxicity) -> Auto-action or escalate -> Admin review -> Log
```

**User Lifecycle:**
```
Join -> Welcome/captcha -> Onboarding -> Active member -> (Violation?) -> Warn/Mute/Ban
```

**Advertiser Pipeline:**
```
Inquiry -> Pricing/availability check -> Payment -> Content review -> Schedule -> Publish -> Report
```

#### What We Should Build

For CIS student communities in Czech Republic, the key differentiator is **educational context awareness**:

1. **Topic-based routing**: Auto-detect message topics (visa, housing, Czech language, jobs) and route to appropriate channels/topics
2. **FAQ automation**: Detect frequently asked questions and auto-respond with curated answers
3. **Event management**: Track university events, deadlines, integrate with academic calendars
4. **Peer verification**: Verify student status (university email, student ID)
5. **Multi-language support**: Czech/Russian/Ukrainian/English content handling

### Existing Tools Worth Evaluating

| Tool | Purpose | Pricing | Notes |
|---|---|---|---|
| **Combot** | Moderation + analytics | Free tier + paid | combot.org, good for basic automation |
| **Controllerbot** | Post scheduling | Free + paid | controllerbot.com, channel management |
| **TGStat** | Analytics | Free tier + paid | tgstat.com, detailed channel analytics |
| **Telemetr** | Analytics | Free tier + paid | telemetr.me, CIS-focused analytics |
| **Rose Bot** | Moderation | Free | Open-source, customizable |
| **GroupHelp** | Moderation | Free + paid | grouphelpbot.xyz |
| **Shieldy** | Anti-spam captcha | Free | Open-source, captcha bot |

---

## 4. Advertising and Monetization

### Telegram Ads Platform

Telegram's official ads platform (https://promote.telegram.org):

- **Minimum budget**: Was 2M EUR initially, then reduced. [VERIFY current minimum -- likely much lower now, possibly ~500-1000 EUR]
- **Format**: Sponsored messages in public channels with 1000+ subscribers
- **Targeting**: By channel topic, language, region
- **Revenue share**: Channel owners get 50% of ad revenue from ads shown in their channels [VERIFY current split]
- **Ad Ton**: Telegram introduced TON-based payments for ads [VERIFY]
- **Restrictions**: No external links in some ad formats, text-only initially (media ads may be available now)

### Direct Ad Sales (Main Revenue for Community Channels)

This is how most CIS Telegram channels actually monetize:

#### Pricing Models
- **Per-post pricing**: Fixed price per sponsored post (most common)
  - Typical range for 10-50k subscriber channels: $50-500 per post
  - For 100k+: $500-5000+ per post
- **CPM (Cost Per Mille)**: $2-15 CPM depending on niche and geo
- **Package deals**: Weekly/monthly packages with multiple posts
- **Pinned post premium**: 2-3x regular post price
- **Story ads**: Newer format, typically 30-50% of regular post price

#### Metrics Advertisers Care About
1. **Reach** (1h, 24h, 48h post views)
2. **ERR** (Engagement Rate by Reach) = reactions+comments+forwards / views
3. **Subscriber growth trend** (organic vs paid)
4. **Audience demographics** (geo, language, interests)
5. **Click-through rate** on links (UTM tracked)

#### Building an Advertiser Self-Service Portal

Architecture for our project:

```
Advertiser Portal (React WebApp)
    |
    v
Backend API (FastAPI or aiogram webhook)
    |
    +-- Ad Slot Manager (calendar, availability)
    +-- Payment Processor (Stars, Stripe, crypto)
    +-- Content Review Queue (admin approval)
    +-- Publishing Engine (Telethon client for posting)
    +-- Analytics Collector (view counts, reactions)
    +-- Report Generator (PDF/HTML reports for advertisers)
```

**Key features for the portal:**
1. **Calendar view** of available ad slots across all channels
2. **Self-service booking** with instant pricing
3. **Content submission** with format guidelines
4. **Payment integration** (Telegram Stars for simple, Stripe for larger deals)
5. **Real-time analytics** dashboard for active campaigns
6. **Post-campaign reports** with screenshots and metrics
7. **Bulk booking** for multi-channel campaigns

**Implementation approach:**
- Extend existing React WebApp with advertiser-facing pages
- Use Telethon to read post view counts (`messages.getMessagesViews`)
- Store ad bookings in PostgreSQL
- Automated post scheduling via Telethon or Bot API
- Webhook notifications for ad status changes

### TON/Crypto Monetization [VERIFY current state]

- Telegram has integrated TON blockchain
- Stars can be converted to/from TON
- Some channels accept crypto payments for ads
- Fragment marketplace for usernames and phone numbers
- **Recommendation**: Support Stars as primary, add TON as optional

---

## 5. Anti-Abuse and Rate Limits

### Bot API Rate Limits

| Operation | Limit |
|---|---|
| Messages to same chat | ~20 messages/minute per chat |
| Messages across all chats | ~30 messages/second total |
| Bulk notifications | 30 messages/second, with retry on 429 |
| Inline query answers | No strict limit, but throttled |
| File uploads | No strict rate, but size limits apply |
| `getUpdates` long polling | Single connection, 30s timeout typical |
| Webhook | Up to 40 updates/second [VERIFY] |
| Group messages | Bot can send ~20/min per group |

**HTTP 429 (Too Many Requests):**
- Response includes `retry_after` field (seconds)
- Always respect this value
- Implement exponential backoff

### Client API (MTProto) Rate Limits

Much stricter and less documented:

| Operation | Approximate Limit |
|---|---|
| Sending messages | ~30/second burst, sustained ~1/second per chat |
| Joining channels | ~20/day for new accounts, more for aged accounts |
| Adding users to groups | ~50-200/day depending on account age |
| Searching messages | Throttled, no exact number published |
| Scraping public channels | Moderate -- avoid more than ~200 requests/minute |
| API calls general | FloodWait errors with wait time in seconds |

### Account Restrictions and Bans

**What gets accounts banned:**
1. Sending unsolicited bulk messages (spam)
2. Joining/leaving many groups rapidly
3. Adding people to groups without their consent
4. Automated actions from freshly created accounts
5. Using unofficial clients that violate ToS
6. Multiple accounts from same phone/IP doing suspicious activities
7. Mass reporting by other users

**Account age matters enormously:**
- New accounts (< 1 week): Very strict limits
- 1-4 weeks: Moderate limits
- 1-6 months: Relaxed limits
- 6+ months: Most relaxed, highest trust

### Best Practices for Running Bots + Userbots

#### Session Management
```python
# Telethon: Use StringSession for containerized deployments
from telethon.sessions import StringSession

# Generate session string once
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print(client.session.save())  # Save this string

# Use in production
client = TelegramClient(StringSession(saved_string), api_id, api_hash)
```

#### Proxy Rotation
- Use SOCKS5 proxies for userbot operations
- Rotate proxies per operation type, not per request
- Residential proxies preferred over datacenter
- Consider MTProto proxies (built into Telegram)
- **Libraries**: `python-socks`, `aiohttp-socks`

```python
# Telethon with proxy
import socks
client = TelegramClient('session', api_id, api_hash,
    proxy=(socks.SOCKS5, 'proxy_host', proxy_port))
```

#### Specific Anti-Ban Strategies

1. **Use dedicated phone numbers** for userbot accounts (not your personal number)
2. **Age the accounts**: Create them, use them normally for a few weeks before automation
3. **Implement natural delays**: Random delays between actions (2-5 seconds)
4. **Respect FloodWait**: Always catch `FloodWaitError` and wait the specified time
5. **Don't parallelize aggressively**: Serial operations are safer
6. **Keep sessions alive**: Don't create/destroy sessions frequently
7. **Monitor for warnings**: Check for "your account may be limited" messages
8. **Separate concerns**: Different accounts for different automation tasks
9. **Use official API parameters**: Don't spoof client version strings

```python
# Proper FloodWait handling in Telethon
from telethon.errors import FloodWaitError
import asyncio

async def safe_send(client, chat, text):
    try:
        await client.send_message(chat, text)
    except FloodWaitError as e:
        print(f"FloodWait: sleeping {e.seconds}s")
        await asyncio.sleep(e.seconds)
        await client.send_message(chat, text)
```

#### For Our Project Specifically

- **Bot account** (via aiogram): All user-facing interactions, moderation commands, webhooks
- **Userbot account** (via Telethon): Background tasks only -- analytics scraping, message history export, ad posting
- **Never mix**: Don't use the userbot for moderation actions that could be reported
- **Rate limit middleware**: We already have aiogram middleware; add similar for Telethon operations

---

## 6. Telegram Analytics

### External Analytics Platforms

#### TGStat (tgstat.com)
- **Largest** Telegram analytics platform
- **API available**: https://api.tgstat.ru/docs/ (paid, starting ~$50/month)
- **Metrics**: Subscribers, views, ERR, reach, growth, audience overlap
- **Coverage**: Excellent for CIS channels, good for global
- **API endpoints**:
  - `channels/stat` -- channel statistics
  - `channels/subscribers` -- subscriber count history
  - `channels/views` -- view statistics
  - `channels/avg-posts-reach` -- average post reach
  - `channels/forwards` -- forward statistics
  - `posts/stat` -- individual post statistics
- **Free tier**: Basic channel info, limited API calls

#### Telemetr (telemetr.me)
- **CIS-focused** analytics platform
- **Strengths**: Audience quality metrics, bot subscriber detection
- **Metrics**: Real subscribers vs bots ratio, audience activity, geo distribution
- **API**: Available but less documented than TGStat

#### Popsters (popsters.com)
- **Cross-platform** analytics (Telegram, VK, Instagram, etc.)
- **Strengths**: Content performance analysis, best posting times
- **Good for**: Comparing performance across platforms

### Custom Analytics (What to Build)

For educational communities, these metrics matter most:

#### Channel-Level Metrics
```
- Subscriber count (daily, weekly, monthly growth)
- Subscriber churn rate
- Average post reach (1h, 24h, 48h)
- Engagement rate (reactions + comments + forwards / views)
- Best posting times (by day of week, hour)
- Content category performance (visa, housing, language, events)
- Audience language distribution
- Forward sources and destinations
```

#### Group/Chat Metrics
```
- Daily active users (DAU)
- Messages per day (by hour, by topic)
- New member join/leave rate
- Most active users (helpers vs lurkers)
- Question response time (how fast do questions get answered)
- Topic distribution (what are people asking about most)
- Moderation actions (mutes, bans, warnings per day)
- Spam rate (caught vs uncaught)
```

#### Advertiser-Facing Metrics
```
- Post impressions (1h, 4h, 24h, 48h)
- Link clicks (via UTM tracking + Telegram URL unfurl stats)
- Post engagement (reactions, comments, forwards)
- Audience retention (% of subscribers who see ad)
- Comparative performance vs organic posts
```

### Implementation Architecture

```python
# Data collection layer (runs periodically via Telethon)

class AnalyticsCollector:
    """Collects raw data from Telegram via Client API."""

    async def collect_channel_stats(self, channel_id: int) -> ChannelStats:
        """Get subscriber count, recent post views, etc."""
        full_channel = await self.client(GetFullChannelRequest(channel_id))
        return ChannelStats(
            subscribers=full_channel.full_chat.participants_count,
            # ...
        )

    async def collect_post_views(self, channel_id: int, message_ids: list[int]):
        """Get view counts for specific posts."""
        views = await self.client(GetMessagesViewsRequest(
            peer=channel_id,
            id=message_ids,
            increment=False
        ))
        return views

    async def collect_chat_activity(self, chat_id: int, days: int = 7):
        """Analyze chat activity for the past N days."""
        messages = []
        async for msg in self.client.iter_messages(chat_id, offset_date=datetime.now()):
            if (datetime.now() - msg.date).days > days:
                break
            messages.append(msg)
        return self._analyze_messages(messages)
```

**Storage**: Use our existing PostgreSQL with new tables:
- `channel_stats_daily` -- daily snapshots of channel metrics
- `post_analytics` -- per-post view/engagement tracking
- `chat_activity_hourly` -- hourly chat activity aggregates
- `user_activity_daily` -- per-user activity metrics
- `ad_campaign_metrics` -- advertiser-specific tracking

**Dashboard**: Extend React WebApp with charts (use Recharts or Chart.js):
- Subscriber growth graph
- Engagement heatmap (by hour/day)
- Content performance comparison
- Moderation activity summary
- Advertiser campaign results

---

## 7. Legal and Compliance (EU/Czech Republic)

### GDPR Considerations

Our bot processes personal data of EU residents (CIS students in Czech Republic), so GDPR applies in full.

#### What Counts as Personal Data in Our Context
- Telegram user IDs (pseudonymous but identifiable)
- Usernames and display names
- Message content
- Phone numbers (if accessed via Client API)
- IP addresses (if webapp is used)
- User behavior patterns (activity data, message frequency)
- Moderation history (mutes, bans, warnings)

#### Required GDPR Measures

1. **Privacy Policy** (mandatory)
   - Must be accessible to all users (link in bot /start message and webapp)
   - Must explain: what data is collected, why, how long it's stored, who has access
   - Must list legal basis for processing
   - Language: Should be in Russian/Ukrainian AND Czech (users' languages)

2. **Legal Basis for Processing**
   - **Legitimate interest** (Art. 6(1)(f)): Moderation, anti-spam -- this is the strongest basis for our use case
   - **Consent** (Art. 6(1)(a)): For optional analytics, cross-chat tracking, advertiser data
   - **Contract** (Art. 6(1)(b)): If we offer paid services via the bot

3. **Data Minimization**
   - Only collect what's necessary for moderation
   - Don't store full message content longer than needed
   - Anonymize/aggregate analytics data where possible

4. **Right to Erasure (Right to be Forgotten)**
   - Users must be able to request deletion of their data
   - Implement a `/deletedata` command or webapp button
   - Must delete within 30 days of request
   - Exception: Can retain ban records for legitimate interest (community safety)

5. **Data Retention Policy**
   - Define clear retention periods:
     - Message logs: 30-90 days (for moderation context)
     - User profiles: Active + 1 year after last activity
     - Ban records: Duration of ban + 1 year
     - Analytics data: Aggregated, kept indefinitely; raw data 90 days
     - Advertiser data: Duration of business relationship + legal retention period
   - Implement automated data cleanup jobs

6. **Data Processing Agreement (DPA)**
   - If using third-party services (TGStat API, cloud hosting, etc.), need DPAs
   - Hosting should be in EU (or with adequate safeguards for non-EU hosting)

7. **Data Protection Impact Assessment (DPIA)**
   - Recommended because we process data at scale and use automated decision-making (AI moderation)
   - Document risks and mitigation measures

#### Czech Republic Specifics

- **Supervisory authority**: UOOU (Urad pro ochranu osobnich udaju) -- https://www.uoou.cz/
- Czech GDPR implementation is close to the regulation text, no major national deviations
- **Language requirement**: Privacy policy should be available in Czech
- **Age considerations**: If serving university students, most are 18+, so no special child protection measures needed (GDPR's age threshold is 16 in CZ, per national law [VERIFY])

### AI/Automated Decision-Making (Art. 22 GDPR)

Our AI moderation agent makes automated decisions (mute, ban, escalate). Under GDPR:

- **Right to explanation**: Users have the right to know they were subject to automated decision-making
- **Right to contest**: Must provide a way to appeal automated moderation decisions
- **Human review**: Significant decisions (bans) should have human review option
- **Our current implementation**: Escalation system already provides this -- good

**Recommendation**: Add a brief notice when AI takes action: "This action was taken by an automated system. Reply to contest." -- which we partially have via the escalation callbacks.

### Telegram Terms of Service Compliance

- **Bot ToS**: https://core.telegram.org/bots/tos [VERIFY URL]
- Key rules:
  - Don't spam users
  - Don't collect data beyond what's needed for bot functionality
  - Don't sell user data
  - Respect user privacy settings
  - Don't use bots for illegal activities
- **Client API ToS**: Stricter. Userbots must not:
  - Spam or harass users
  - Scrape data for sale
  - Impersonate Telegram
  - Flood the API
  - Automation must not look like abuse

### Practical Compliance Checklist

- [ ] Draft privacy policy (RU/UA/CZ/EN)
- [ ] Add privacy policy link to bot /start and /help
- [ ] Implement `/deletedata` command
- [ ] Set up data retention automation (cleanup cron job)
- [ ] Document legal basis for each data processing activity
- [ ] Add AI decision notice to automated moderation actions
- [ ] Implement appeal mechanism for all automated actions (partially done via escalation)
- [ ] Choose EU-based hosting or ensure adequate safeguards
- [ ] Create DPA template for third-party services
- [ ] Set up data access logging (who accessed what data)

---

## 8. Architecture Recommendations for Our Project

### Proposed System Architecture

```
                    +-------------------+
                    |   Telegram Cloud  |
                    +--------+----------+
                             |
              +--------------+--------------+
              |                             |
    +---------v---------+     +-------------v-----------+
    |  Bot API (aiogram)|     | Client API (Telethon)   |
    |  - Moderation     |     | - Analytics collection  |
    |  - User commands  |     | - Message history       |
    |  - WebApp serving |     | - Ad posting            |
    |  - Payments       |     | - Cross-chat tracking   |
    |  - Callbacks      |     | - User info lookup      |
    +---------+---------+     +-------------+-----------+
              |                             |
              +----------+--+---------------+
                         |
              +----------v-----------+
              |    Application Core  |
              |  - Use cases         |
              |  - Domain entities   |
              |  - Business rules    |
              +----------+-----------+
                         |
         +---------------+---------------+
         |               |               |
+--------v------+ +------v------+ +------v--------+
| PostgreSQL    | | Redis       | | File Storage  |
| - Users       | | - Cache     | | - Media       |
| - Chats       | | - Sessions  | | - Reports     |
| - Analytics   | | - Rate limit| | - Exports     |
| - Ads         | | - Queues    | |               |
+---------------+ +-------------+ +---------------+
         |
+--------v--------------+
|   React WebApp         |
|  - Admin panel         |
|  - Advertiser portal   |
|  - Analytics dashboard |
+------------------------+
```

### Implementation Phases

**Phase 1 (Current + Near-term)**
- Solidify existing bot moderation (aiogram) -- DONE
- Complete WebApp admin panel -- IN PROGRESS
- Add comprehensive logging and basic analytics to PostgreSQL

**Phase 2 (Add Client API Layer)**
- Set up Telethon userbot alongside aiogram bot
- Implement message history collection for managed chats
- Build analytics data collection pipeline
- Add cross-chat user tracking

**Phase 3 (Analytics Dashboard)**
- Extend React WebApp with analytics views
- Integrate TGStat API for external benchmarking
- Build custom metrics (educational community-specific)
- Automated daily/weekly reports

**Phase 4 (Advertiser Platform)**
- Ad slot calendar and booking system
- Advertiser self-service portal (React WebApp extension)
- Payment integration (Telegram Stars + Stripe)
- Campaign analytics and reporting
- Content review workflow

**Phase 5 (Full Autonomy)**
- AI-powered content suggestions
- Automated FAQ responses based on message history analysis
- Smart scheduling (optimal posting times based on analytics)
- Cross-channel content syndication
- Advertiser matching (based on audience interests)

### Technology Additions Needed

| Component | Technology | Purpose |
|---|---|---|
| Client API | Telethon | MTProto operations |
| Task queue | Celery + Redis or arq | Background jobs (analytics, reports) |
| Cache | Redis | Rate limiting, session cache, API cache |
| Charts | Recharts (React) | Analytics visualization |
| PDF reports | WeasyPrint or reportlab | Advertiser reports |
| Scheduler | APScheduler or Celery Beat | Periodic data collection |
| Payments | Telegram Stars API + Stripe | Monetization |

### Key Technical Decisions

1. **Telethon session storage**: Use StringSession stored as encrypted env variable, not file-based
2. **Analytics data retention**: Raw data 90 days, aggregated indefinitely
3. **Separation of concerns**: Telethon client runs as separate service/worker, communicates via Redis queue with main bot
4. **Rate limiting**: Central rate limiter in Redis, shared between bot and userbot
5. **Multi-chat management**: Single bot instance manages all chats; Telethon client joins all managed chats

---

## Key Reference Links

### Official Telegram Documentation
- Bot API: https://core.telegram.org/bots/api
- MTProto API: https://core.telegram.org/api
- Mini Apps/WebApps: https://core.telegram.org/bots/webapps
- TDLib (C++ client): https://core.telegram.org/tdlib
- Bot Payments: https://core.telegram.org/bots/payments
- Telegram Ads: https://promote.telegram.org

### Libraries
- aiogram: https://github.com/aiogram/aiogram (our current framework)
- Telethon: https://github.com/LonamiWebs/Telethon
- Pyrogram: https://github.com/pyrogram/pyrogram
- Bot API local server: https://github.com/tdlib/telegram-bot-api

### Analytics Platforms
- TGStat: https://tgstat.com / API: https://api.tgstat.ru/docs/
- Telemetr: https://telemetr.me
- Popsters: https://popsters.com

### Czech Republic / EU Compliance
- UOOU (Czech DPA): https://www.uoou.cz/
- GDPR full text: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Czech Act on Personal Data Processing: Act No. 110/2019 Coll.

---

*This document should be treated as a living reference. Items marked [VERIFY] should be checked against the latest documentation as of the current date. Telegram updates its APIs frequently -- check https://core.telegram.org/bots/api#recent-changes for the latest Bot API changes.*
