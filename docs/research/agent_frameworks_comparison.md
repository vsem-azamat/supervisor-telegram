# Multi-Agent Orchestration Frameworks: Comprehensive Comparison (2025-2026)

**Date:** 2026-03-06
**Context:** Evaluating LangGraph alternatives for an async Python Telegram bot ecosystem (PydanticAI, PostgreSQL, aiogram, long-running agents, human-in-the-loop).
**Knowledge cutoff:** May 2025. Items after that date are marked **[VERIFY]**.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Framework Evaluations](#framework-evaluations)
3. [Comparison Matrix](#comparison-matrix)
4. [Recommendation for Our Stack](#recommendation)

---

## Executive Summary

LangGraph (part of the LangChain ecosystem) pioneered stateful multi-agent graphs in Python but carries significant LangChain baggage: deep abstraction layers, opaque debugging, LCEL complexity, and vendor-tilted defaults. The 2025 wave of alternatives offers cleaner designs. After evaluating 13+ frameworks, the top contenders for our async Python/PostgreSQL/Telegram stack are:

- **PydanticAI** (already in use) -- excellent for single-agent, tool-calling patterns
- **Google ADK** -- strong multi-agent orchestration with clean async design
- **OpenAI Agents SDK** -- minimal, composable, good DX but OpenAI-tilted
- **Burr** -- lightweight state machines, perfect for long-running workflows with checkpointing

The recommendation is at the end of this document.

---

## Framework Evaluations

### 1. Google ADK (Agent Development Kit)

**Released:** April 2025 (open-sourced at Cloud Next '25)
**License:** Apache 2.0
**Repo:** google/adk-python

#### Overview
Google's ADK is a full-featured agent framework designed for building, deploying, and orchestrating multi-agent systems. It was built from the ground up (not a wrapper around existing libraries) and emphasizes composability and production readiness.

#### API Design & DX
- Clean, decorator-based tool definitions (similar to PydanticAI)
- Agent definition is declarative: model, tools, instructions, sub-agents
- Built-in agent types: LlmAgent, SequentialAgent, ParallelAgent, LoopAgent
- Supports "agent-as-tool" pattern for hierarchical composition
- Good type hints, Pydantic integration for tool parameters
- **Rating: 8/10** -- Modern, clean API. Slightly over-engineered for simple cases.

#### Multi-Agent Orchestration
- First-class support: agents can delegate to sub-agents via transfer functions
- Built-in orchestration patterns: sequential, parallel, loop, conditional routing
- Agent-to-agent communication through shared session state
- Supports dynamic agent selection at runtime
- **Rating: 9/10** -- One of the strongest multi-agent stories.

#### Persistence / Checkpointing
- Session-based state management with pluggable backends
- Built-in InMemorySessionService and DatabaseSessionService
- Session state persists across turns; supports long-running conversations
- **[VERIFY]** PostgreSQL support may require custom SessionService implementation
- **Rating: 7/10** -- Good foundations, may need custom work for PostgreSQL.

#### Human-in-the-Loop (HITL)
- Supports approval workflows via callback mechanisms
- Agents can pause execution and request human input
- **Rating: 7/10** -- Workable but not as polished as LangGraph's interrupt/resume.

#### Async Python Support
- Fully async from the ground up (asyncio native)
- Uses `async def` for tools and agent execution
- Compatible with async ORMs and frameworks
- **Rating: 9/10**

#### Maturity & Community
- Backed by Google, active development
- Released April 2025, rapidly evolving
- Growing community but still young
- Documentation improving but gaps exist
- **[VERIFY]** Community size as of early 2026
- **Rating: 6/10** -- Still young, but strong corporate backing.

#### Vendor Lock-in
- Designed for Google models (Gemini) but supports other providers via LiteLLM or custom model wrappers
- Tight integration with Vertex AI for deployment
- Can be used standalone without Google Cloud
- **Rating: 6/10** -- Some Google tilt, but usable independently.

---

### 2. OpenAI Agents SDK (formerly Swarm)

**Released:** March 2025
**License:** MIT
**Repo:** openai/openai-agents-python

#### Overview
OpenAI's production successor to the experimental Swarm framework. Minimal, opinionated, focused on simplicity. The core primitives are Agents, Handoffs, and Guardrails.

#### API Design & DX
- Extremely clean, minimal API surface
- Agent = model + instructions + tools + handoffs
- `Runner.run()` for single execution, `Runner.run_streamed()` for streaming
- Handoffs are just tools that transfer control to another agent
- Tracing built-in (OpenAI dashboard or custom exporters)
- Pydantic for structured outputs
- **Rating: 9/10** -- Best DX of any framework evaluated. Opinionated simplicity.

#### Multi-Agent Orchestration
- Handoff-based: agents transfer control via handoff tools
- No built-in complex orchestration patterns (no parallel, no graph)
- Works well for linear delegation chains and triage patterns
- For complex flows, you orchestrate manually with Python
- **Rating: 6/10** -- Simple handoffs only. Complex orchestration is DIY.

#### Persistence / Checkpointing
- No built-in persistence or checkpointing
- Stateless by design -- you manage state externally
- RunContext can carry arbitrary data per run
- **Rating: 3/10** -- You build your own persistence layer.

#### Human-in-the-Loop
- No native HITL mechanism
- Can be implemented via custom tools that block/await
- **Rating: 3/10** -- Manual implementation required.

#### Async Python Support
- Fully async (`Runner.run()` is async)
- Clean asyncio integration
- **Rating: 9/10**

#### Maturity & Community
- Backed by OpenAI, MIT licensed
- Simple enough that there's less to break
- Active development, good docs
- **Rating: 7/10** -- Simple = stable. But limited scope.

#### Vendor Lock-in
- Designed for OpenAI models but supports custom model providers via `set_default_openai_client()` or model override
- Tracing defaults to OpenAI dashboard
- **Rating: 5/10** -- Usable with other providers but clearly OpenAI-first.

---

### 3. CrewAI v2/v3

**Released:** v2 late 2024, v3 **[VERIFY]** 2025
**License:** MIT (core), Enterprise tier exists
**Repo:** crewAIInc/crewAI

#### Overview
CrewAI popularized the "crew of agents with roles" metaphor. v1 had significant issues (LangChain dependency, poor error handling, flaky execution). v2 removed the LangChain dependency and rewrote internals. v3 **[VERIFY]** may have added further improvements.

#### API Design & DX
- Role-based agent definition: Agent(role, goal, backstory, tools)
- Task-based workflow: Task(description, agent, expected_output)
- Crew orchestrates tasks across agents
- Decorators for tool creation (`@tool`)
- Flows API for complex orchestration (added in v2)
- **Rating: 6/10** -- Intuitive metaphor but verbose. "Backstory" feels gimmicky for production.

#### Multi-Agent Orchestration
- Sequential and hierarchical process types
- Crew Flows for custom orchestration logic
- Agents can delegate to other agents
- Task dependencies and conditional routing
- **Rating: 7/10** -- Good for structured workflows.

#### Persistence / Checkpointing
- Crew memory system: short-term, long-term, entity memory
- Uses embeddings for memory search
- **[VERIFY]** PostgreSQL support for memory backends
- No native workflow checkpointing (can't resume mid-crew)
- **Rating: 5/10** -- Memory yes, checkpointing no.

#### Human-in-the-Loop
- `human_input=True` on tasks for approval
- Basic: prompts for input during execution
- Not designed for async HITL (e.g., "wait for Telegram callback")
- **Rating: 4/10** -- Blocking input only.

#### Async Python Support
- Added async execution in v2 (`crew.kickoff_async()`)
- Internal implementation still has sync components
- Some tools and integrations remain synchronous
- **Rating: 5/10** -- Partial async.

#### Maturity & Community
- Large community, many tutorials and examples
- Significant enterprise adoption
- Quality concerns: many open issues, breaking changes between versions
- **Rating: 7/10** -- Popular but rough edges.

#### Vendor Lock-in
- Model-agnostic via LiteLLM
- CrewAI Enterprise adds proprietary features
- **Rating: 8/10** -- Low lock-in for open-source tier.

---

### 4. AutoGen AG2 / AutoGen 0.4+

**Released:** AutoGen 0.4 rewrite late 2024, AG2 fork early 2025
**License:** Apache 2.0 (0.4), Apache 2.0 (AG2)
**Repos:** microsoft/autogen (0.4+), ag2ai/ag2

#### Overview
Microsoft's AutoGen was a pioneer in multi-agent conversation but had a messy v0.2 API. The 0.4 rewrite (`autogen-agentchat` + `autogen-core`) is a ground-up redesign with proper abstractions. AG2 is a community fork that diverged when Microsoft changed direction.

**Note:** The situation is confusing. Microsoft's official AutoGen 0.4 (`autogen-agentchat`) and the community AG2 fork are separate projects with different APIs.

#### API Design & DX (AutoGen 0.4)
- `autogen-core`: low-level actor-based messaging framework
- `autogen-agentchat`: high-level multi-agent conversations
- Clean separation but two packages to learn
- AssistantAgent, UserProxyAgent, GroupChat patterns
- **Rating: 6/10** -- Improved over 0.2 but still complex. Two-package model is confusing.

#### Multi-Agent Orchestration
- GroupChat with configurable speaker selection
- Swarm-style handoffs
- Teams: RoundRobinGroupChat, SelectorGroupChat, MagenticOneGroupChat
- Termination conditions are composable
- **Rating: 8/10** -- Strong orchestration primitives.

#### Persistence / Checkpointing
- State can be serialized/deserialized
- **[VERIFY]** Built-in checkpointing support in 0.4
- No native database persistence layer
- **Rating: 4/10** -- Basic serialization, no production persistence.

#### Human-in-the-Loop
- UserProxyAgent designed for human interaction
- Handoff mechanism can route to human agents
- **Rating: 6/10** -- Designed for it, but primarily for CLI/notebook interaction.

#### Async Python Support
- 0.4 is fully async (asyncio native)
- `autogen-core` uses an async event-driven architecture
- **Rating: 8/10**

#### Maturity & Community
- Microsoft-backed, large community
- 0.4 rewrite means effectively a new framework (limited battle-testing)
- AG2 fork creates community fragmentation
- **[VERIFY]** Status of AG2 vs AutoGen 0.4 convergence
- **Rating: 5/10** -- Community split hurts adoption confidence.

#### Vendor Lock-in
- Model-agnostic (supports OpenAI, Anthropic, local models)
- No cloud service dependency
- **Rating: 9/10** -- Very low lock-in.

---

### 5. Llama Stack

**Released:** 2024-2025 (evolving)
**License:** MIT
**Repo:** meta-llama/llama-stack

#### Overview
Meta's framework for building applications with Llama models. More of a model-serving and tool-use framework than a multi-agent orchestration system. Provides standardized APIs for inference, safety, memory, and tool use.

#### API Design & DX
- REST API-first design with Python client
- Providers pattern for pluggable backends
- Focused on model serving, not agent orchestration
- **Rating: 5/10** -- Not really an agent framework.

#### Multi-Agent Orchestration
- No built-in multi-agent support
- Single-agent with tools is the primary pattern
- **Rating: 2/10** -- Not designed for this.

#### Persistence / Checkpointing
- Memory banks (vector, key-value, keyword)
- Agent session persistence
- **Rating: 5/10** -- Basic agent memory.

#### Human-in-the-Loop
- Not a focus
- **Rating: 2/10**

#### Async Python Support
- Async client available
- **Rating: 6/10**

#### Maturity & Community
- Meta-backed, growing ecosystem
- Focused on Llama model family
- **Rating: 5/10**

#### Vendor Lock-in
- Strongly tied to Llama models
- **Rating: 3/10** -- High lock-in to Meta's model family.

**Verdict:** Not suitable for multi-agent orchestration. Better suited as an inference backend.

---

### 6. Semantic Kernel

**Released:** 2023, actively maintained through 2025
**License:** MIT
**Repo:** microsoft/semantic-kernel

#### Overview
Microsoft's SDK for integrating LLMs into applications. Originally C#-focused, now has a Python SDK. More of an LLM integration framework than a pure agent orchestration tool, but has been adding agent capabilities.

#### API Design & DX
- Plugin-based architecture (functions grouped into plugins)
- Kernel object as the central orchestrator
- Planner system for automatic function chaining
- Python SDK feels like a port from C# (not Pythonic)
- **Rating: 5/10** -- Enterprise-y, not Pythonic. Too many abstractions.

#### Multi-Agent Orchestration
- AgentGroupChat for multi-agent conversations (added 2024-2025)
- Agent types: ChatCompletionAgent, OpenAIAssistantAgent
- Selection strategies for turn-taking
- **[VERIFY]** Improvements to multi-agent in 2025-2026
- **Rating: 5/10** -- Basic multi-agent, not the primary focus.

#### Persistence / Checkpointing
- Memory connectors (various vector stores)
- Conversation history management
- No native workflow checkpointing
- **Rating: 5/10**

#### Human-in-the-Loop
- Function call filtering for approval workflows
- Auto-invoke vs manual invoke control
- **Rating: 5/10** -- Possible but not elegant.

#### Async Python Support
- Async support available but feels bolted on
- C# is the primary target
- **Rating: 5/10**

#### Maturity & Community
- Large community (especially .NET)
- Python SDK is secondary citizen
- Microsoft backing ensures longevity
- **Rating: 6/10** -- Mature for C#, less so for Python.

#### Vendor Lock-in
- Model-agnostic
- Azure-friendly but not required
- **Rating: 8/10**

**Verdict:** Better fit for .NET shops. Python DX is subpar compared to alternatives.

---

### 7. BeeAI / Bee Agent Framework

**Released:** 2024-2025
**License:** Apache 2.0
**Repo:** i-am-bee/bee-agent-framework (TypeScript), Python version **[VERIFY]**

#### Overview
IBM's open-source agent framework. Originally TypeScript-focused. Emphasizes reliability and observability. The BeeAI platform aims to be a multi-framework orchestration layer.

#### API Design & DX
- TypeScript-first (Python support unclear/limited)
- ReAct-based agent loop
- Tool abstraction with validation
- **Rating: 4/10** for Python -- TypeScript focus is a dealbreaker for our stack.

#### Multi-Agent Orchestration
- **[VERIFY]** Multi-agent capabilities via BeeAI platform
- Single-agent focus in the framework itself
- **Rating: 4/10**

#### Persistence / Checkpointing
- Serializable state
- **Rating: 4/10**

#### Human-in-the-Loop
- **[VERIFY]** Status unclear
- **Rating: 3/10**

#### Async Python Support
- TypeScript-native, Python support uncertain
- **Rating: 2/10**

#### Maturity & Community
- IBM-backed but small community
- **Rating: 3/10**

#### Vendor Lock-in
- Open source, model-agnostic
- **Rating: 8/10**

**Verdict:** Not viable for our Python async stack. TypeScript-first.

---

### 8. Burr

**Released:** 2024, actively maintained through 2025
**License:** Apache 2.0
**Repo:** DAGWorks-Inc/burr
**Created by:** Hamilton team (DAGWorks)

#### Overview
Burr is a lightweight framework for building stateful, long-running applications as state machines. Not AI-specific -- it's a general state machine framework that happens to work excellently for agent orchestration. This is its superpower: no magic, no LLM-specific abstractions, just clean state management.

#### API Design & DX
- State machine with explicit states and transitions
- `@action` decorator for state transitions
- Conditions for branching logic
- Reads/writes declarations for state access
- Pure Python, minimal dependencies
- **Rating: 9/10** -- Beautifully simple. You understand what's happening.

#### Multi-Agent Orchestration
- Not built-in, but easily composed
- Each agent can be a Burr application or a set of states
- Orchestration is explicit Python code, not framework magic
- **Rating: 5/10** -- DIY multi-agent, but the primitives are solid.

#### Persistence / Checkpointing
- **First-class checkpointing** -- this is Burr's killer feature
- Built-in persisters: SQLite, PostgreSQL, Redis, S3
- `PostgreSQLPersister` works with async (`asyncpg`)
- Full state serialization at every step
- Resume from any checkpoint
- Time-travel debugging
- **Rating: 10/10** -- Best persistence story of any framework evaluated.

#### Human-in-the-Loop
- Natural fit: define a "wait_for_human" state that pauses the machine
- Resume with human input by providing the next state transition
- Works perfectly with async patterns (await callback, resume later)
- **Rating: 9/10** -- State machines are ideal for HITL.

#### Async Python Support
- Full async support
- Async actions, async persisters
- **Rating: 9/10**

#### Maturity & Community
- Small but high-quality community
- Hamilton team is experienced and responsive
- Excellent documentation and examples
- Used in production by several companies
- Built-in Burr UI for visualization and debugging
- **Rating: 6/10** -- Small community, but high quality.

#### Vendor Lock-in
- Zero lock-in. No model opinions, no cloud dependencies
- Pure state machine -- bring your own everything
- **Rating: 10/10**

**Verdict:** Excellent fit for long-running, checkpointed agents with HITL. The "boring technology" choice -- and that's a compliment.

---

### 9. ControlFlow

**Released:** 2024
**License:** Apache 2.0
**Repo:** PrefectHQ/ControlFlow
**Created by:** Prefect (workflow orchestration company)

#### Overview
Prefect's take on agent orchestration. Uses a "task-centric" approach where you define tasks with expected result types, and agents complete them. Built on top of Prefect's workflow engine concepts.

#### API Design & DX
- Task-centric: `cf.Task(objective, result_type, agents)`
- Flow decorator for orchestration: `@cf.flow`
- Agents are configured with models and tools
- Pydantic for result types
- **Rating: 7/10** -- Clean task abstraction. Slightly magical.

#### Multi-Agent Orchestration
- Multiple agents can collaborate on tasks
- Agent assignment to tasks (explicit or dynamic)
- Flow-level orchestration with dependencies
- **Rating: 6/10** -- Task-focused, not conversational multi-agent.

#### Persistence / Checkpointing
- Leverages Prefect's persistence infrastructure
- Task results are cached and stored
- **[VERIFY]** State persistence between flow runs
- **Rating: 6/10** -- Good if you're already using Prefect.

#### Human-in-the-Loop
- Tasks can require human input
- **[VERIFY]** Async HITL support
- **Rating: 5/10**

#### Async Python Support
- Async support available
- **Rating: 7/10**

#### Maturity & Community
- Prefect-backed, relatively small community for the agent framework specifically
- **[VERIFY]** Whether ControlFlow is still actively maintained in 2026
- **Rating: 5/10**

#### Vendor Lock-in
- Model-agnostic
- Benefits from Prefect Cloud but doesn't require it
- **Rating: 7/10**

---

### 10. Temporal / Prefect + LLM (Workflow Engines for Agents)

#### Overview
Using production workflow orchestration engines (Temporal, Prefect) as the backbone for agent systems, rather than purpose-built agent frameworks. The idea: LLM calls are just activities/tasks within a durable workflow.

#### Temporal

- **Durable execution**: workflows survive process restarts, deploys, crashes
- **Activity-based**: LLM calls, tool executions are activities with retry policies
- **Timer and signal support**: perfect for HITL (signal = human response)
- **Python SDK**: fully async, production-grade
- **Checkpointing**: automatic, transparent, event-sourced
- **Multi-agent**: model as multiple workflows communicating via signals/child workflows

**Pros:**
- Battle-tested at massive scale (Uber, Netflix, Stripe)
- True durability -- no state loss ever
- Excellent for long-running processes (days, weeks)
- Built-in retry, timeout, cancellation
- Perfect for "wait for human callback" patterns

**Cons:**
- Requires running Temporal server (or Temporal Cloud)
- Significant operational overhead
- Not designed for LLM patterns (no streaming, tool-call abstractions)
- Verbose workflow definitions for simple agent tasks
- Learning curve is steep

**Rating for our use case:** 7/10 for durability, 4/10 for DX with LLMs.

#### Prefect

- Lighter weight than Temporal
- Good Python DX with decorators
- Cloud or self-hosted
- Less durable than Temporal (not event-sourced)

**Verdict:** Temporal is overkill for most agent use cases but is the right answer if you need absolute durability for long-running processes. Consider a hybrid: lightweight agent framework (PydanticAI/Burr) with Temporal for the outer workflow when durability is critical.

---

### 11. Other Notable Frameworks

#### PydanticAI (Already in use)
- **Rating: 8/10 for single-agent**
- Excellent DX, Pydantic-native, async, model-agnostic
- Weak multi-agent story (no built-in orchestration)
- No persistence/checkpointing
- Our current choice for the agent layer; works well for individual agent tasks

#### LangGraph (The incumbent we're replacing)
- **Rating: 7/10 overall**
- Strong multi-agent and HITL support
- LangChain baggage, LCEL complexity, over-abstraction
- Good checkpointing (StateGraph with persistence backends)
- We're moving away from this due to DX friction

#### Haystack 2.x (deepset)
- Pipeline-based, good for RAG, less for agent orchestration
- Not a multi-agent framework
- **Rating: 4/10** for our use case

#### DSPy (Stanford)
- Prompt optimization framework, not agent orchestration
- Interesting for prompt engineering but orthogonal to our needs
- **Rating: 3/10** for our use case

#### Instructor
- Structured output extraction, not agent orchestration
- Complementary to PydanticAI (similar philosophy)
- **Rating: 2/10** for multi-agent (not designed for it)

#### Magentic-One (Microsoft Research) [VERIFY]
- Research multi-agent system built on AutoGen
- Specialized team: Orchestrator, WebSurfer, FileSurfer, Coder, ComputerTerminal
- Not a general-purpose framework
- **Rating: 3/10** for our use case

#### smolagents (Hugging Face) [VERIFY]
- Lightweight agent framework from HuggingFace
- Code-based agents (agents write Python code as actions)
- Simple, minimal, good for quick prototypes
- Limited multi-agent, no persistence
- **Rating: 5/10** -- interesting but too simple for our needs

---

## Comparison Matrix

| Framework | API/DX | Multi-Agent | Persistence | HITL | Async | Maturity | Lock-in (low=bad) | **Total /70** |
|-----------|--------|-------------|-------------|------|-------|----------|--------------------|---------------|
| **Google ADK** | 8 | 9 | 7 | 7 | 9 | 6 | 6 | **52** |
| **OpenAI Agents SDK** | 9 | 6 | 3 | 3 | 9 | 7 | 5 | **42** |
| **CrewAI v2** | 6 | 7 | 5 | 4 | 5 | 7 | 8 | **42** |
| **AutoGen 0.4** | 6 | 8 | 4 | 6 | 8 | 5 | 9 | **46** |
| **Llama Stack** | 5 | 2 | 5 | 2 | 6 | 5 | 3 | **28** |
| **Semantic Kernel** | 5 | 5 | 5 | 5 | 5 | 6 | 8 | **39** |
| **BeeAI** | 4 | 4 | 4 | 3 | 2 | 3 | 8 | **28** |
| **Burr** | 9 | 5 | 10 | 9 | 9 | 6 | 10 | **58** |
| **ControlFlow** | 7 | 6 | 6 | 5 | 7 | 5 | 7 | **43** |
| **Temporal+LLM** | 5 | 6 | 10 | 9 | 8 | 10 | 7 | **55** |
| **PydanticAI** | 9 | 3 | 3 | 4 | 9 | 7 | 9 | **44** |

**Scoring weights for our stack (long-running, HITL, async, PostgreSQL):**
Persistence and HITL should be weighted 2x for our use case. Adjusted scores:

| Framework | Adjusted Total /90 | Notes |
|-----------|--------------------|-|
| **Burr** | **77** | Best persistence + HITL + async |
| **Temporal+LLM** | **74** | Best durability, worst DX for LLMs |
| **Google ADK** | **66** | Best multi-agent, decent overall |
| **AutoGen 0.4** | **56** | Strong orchestration, fragmented community |
| **PydanticAI** | **51** | Great DX, needs persistence layer |
| **OpenAI Agents SDK** | **48** | Great DX, needs everything else |
| **ControlFlow** | **54** | Decent all-around |
| **CrewAI v2** | **51** | Popular but poor async/HITL |

---

## Recommendation for Our Stack {#recommendation}

### Our Requirements Recap
- Python async (aiogram, SQLAlchemy async, asyncio)
- PostgreSQL as primary database
- Telegram bot with callback-based HITL (inline buttons, admin approval)
- Long-running agents (moderation decisions that may need human review hours later)
- PydanticAI already in use for agent core
- Clean architecture (DDD, no framework lock-in)

### Recommended Architecture: PydanticAI + Burr (Layered Approach)

```
Layer 1: Agent Intelligence  -->  PydanticAI (already in use)
Layer 2: Workflow / State     -->  Burr (new addition)
Layer 3: Persistence          -->  Burr PostgreSQLPersister
Layer 4: Presentation         -->  aiogram (already in use)
```

#### Why This Combination

**Keep PydanticAI** for what it does well:
- LLM tool-calling, structured outputs, model-agnostic inference
- Clean Pydantic integration for our domain types
- Already integrated and working in `app/agent/core.py`

**Add Burr** for what PydanticAI lacks:
- **State machine orchestration:** Model the moderation workflow as explicit states (analyze -> decide -> escalate -> wait_for_human -> execute). Each state is visible, debuggable, resumable.
- **PostgreSQL checkpointing:** Burr's `PostgreSQLPersister` gives us durable state storage using our existing database. Every state transition is persisted. If the bot restarts, agents resume from their last checkpoint.
- **HITL as a state:** The "wait for admin approval" step is just a state in the machine. When the Telegram callback comes in (could be minutes or hours later), we load the Burr application from the checkpoint and transition to the next state.
- **No vendor lock-in:** Burr has zero opinions about LLMs. It's a state machine library. We keep full control.
- **Burr UI:** Free debugging/visualization tool to see agent state machines in action.

#### Implementation Sketch

```python
from burr.core import ApplicationBuilder, State, action, when

@action(reads=["message"], writes=["analysis"])
async def analyze_message(state: State) -> State:
    """Use PydanticAI agent to analyze the message."""
    result = await agent_core.analyze(state["message"])
    return state.update(analysis=result)

@action(reads=["analysis"], writes=["decision", "needs_human"])
async def make_decision(state: State) -> State:
    """Decide action based on analysis."""
    analysis = state["analysis"]
    if analysis.confidence < 0.7:
        return state.update(decision="escalate", needs_human=True)
    return state.update(decision=analysis.action, needs_human=False)

@action(reads=["decision"], writes=["escalation_id"])
async def escalate_to_admin(state: State) -> State:
    """Send to admin via Telegram and wait."""
    esc_id = await escalation_service.create(state["message"], state["analysis"])
    return state.update(escalation_id=esc_id)

@action(reads=["human_decision"], writes=["final_action"])
async def apply_human_decision(state: State) -> State:
    """Apply the admin's decision."""
    return state.update(final_action=state["human_decision"])

# Build the application
app = (
    ApplicationBuilder()
    .with_actions(analyze_message, make_decision, escalate_to_admin, apply_human_decision)
    .with_transitions(
        ("analyze_message", "make_decision"),
        ("make_decision", "escalate_to_admin", when(needs_human=True)),
        ("make_decision", "execute_action", when(needs_human=False)),
        ("escalate_to_admin", "wait_for_human"),  # pauses here
        ("wait_for_human", "apply_human_decision"),
        ("apply_human_decision", "execute_action"),
    )
    .with_state(message=incoming_message)
    .with_tracker(PostgreSQLPersister(connection_string=settings.database.url))
    .build()
)
```

When a Telegram callback arrives:
```python
# Resume from checkpoint
app = ApplicationBuilder() \
    .with_persister(pg_persister) \
    .initialize_from(tracker, resume_at_next_action=True, partition_key=escalation_id) \
    .build()

# Provide human decision and continue
app.update_state({"human_decision": callback_data})
await app.astep()  # transitions from wait_for_human -> apply_human_decision
```

#### Migration Path

1. **Phase 1 (low risk):** Add Burr as a dependency. Define the moderation workflow as a Burr state machine. Keep PydanticAI agent calls inside Burr actions. Wire up PostgreSQL persister.

2. **Phase 2:** Migrate escalation service (`app/agent/escalation.py`) to use Burr state machines instead of raw DB state management. The current `EscalationService` already does manual state tracking -- Burr replaces that with a proper framework.

3. **Phase 3:** Add Burr UI for debugging/monitoring agent workflows.

### Alternatives Considered

**Google ADK** -- Strong second choice if we need true multi-agent delegation (e.g., one agent for spam detection, another for welcome messages, a coordinator agent). Currently our agent architecture is single-agent-with-tools, so ADK's multi-agent strengths aren't needed yet. Revisit if we add specialized sub-agents.

**Temporal** -- Right choice if we discover that Burr's persistence isn't durable enough (e.g., we need exactly-once guarantees across distributed deployments). Significant operational overhead. Hold in reserve.

**OpenAI Agents SDK** -- Great DX but doesn't solve our actual problems (persistence, HITL). Would replace PydanticAI rather than complement it, with no clear benefit.

### Final Verdict

**Burr** wins because it solves the exact problems we have (state persistence, HITL, resumability) without replacing what already works (PydanticAI for LLM intelligence, aiogram for Telegram). It's the "boring infrastructure" choice: a well-engineered state machine library with PostgreSQL persistence, not an AI hype framework. That's exactly what a production Telegram bot needs.

```
pip install burr[postgresql]  # or: uv add "burr[postgresql]"
```

---

*Document compiled from training knowledge with cutoff May 2025. Items marked [VERIFY] should be confirmed with current sources.*
