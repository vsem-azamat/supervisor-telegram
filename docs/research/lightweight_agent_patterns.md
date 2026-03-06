# Lightweight Multi-Agent Patterns: Alternatives to Heavy Frameworks

**Date:** 2026-03-06
**Context:** Python async Telegram bot with PydanticAI + custom orchestration. Exploring the middle ground between "everything from scratch" and heavyweight frameworks like LangGraph.
**Knowledge cutoff:** Mid-2025. Items marked [VERIFY] need confirmation against current docs.

---

## Table of Contents

1. [PydanticAI Multi-Agent Patterns](#1-pydanticai-multi-agent-patterns)
2. [Instructor (Jason Liu)](#2-instructor-jason-liu)
3. [Workflow Engines: Prefect / Temporal / Dramatiq](#3-workflow-engines-prefect--temporal--dramatiq)
4. [Asyncio-Native Patterns](#4-asyncio-native-patterns)
5. ["Agents Are Just Loops" -- Minimalist Approaches](#5-agents-are-just-loops----minimalist-approaches)
6. [Burr -- Hamilton's State Machine Agent Framework](#6-burr----hamiltons-state-machine-agent-framework)
7. [ControlFlow -- Prefect's AI Agent Framework](#7-controlflow----prefects-ai-agent-framework)
8. [DSPy -- Prompt Optimization vs. Orchestration](#8-dspy----prompt-optimization-vs-orchestration)
9. [Mirascope -- Lightweight LLM Toolkit](#9-mirascope----lightweight-llm-toolkit)
10. [FastAPI + Background Tasks as Microservice Agents](#10-fastapi--background-tasks-as-microservice-agents)
11. [Decision Matrix](#11-decision-matrix)
12. [Recommendation](#12-recommendation)

---

## 1. PydanticAI Multi-Agent Patterns

### What PydanticAI Provides

PydanticAI (by the Pydantic team, Samuel Colvin) is a thin, type-safe wrapper around LLM calls. Its core abstractions:

- **Agent** -- a callable that takes dependencies + a prompt, returns a typed result
- **Tools** -- Python functions decorated with `@agent.tool`, automatically schema-generated from type hints
- **Structured output** -- result type validated via Pydantic models
- **Dependency injection** -- typed `deps` passed to tools at runtime
- **Streaming** -- async streaming with typed partial results

### Multi-Agent Patterns in PydanticAI

PydanticAI does NOT have a built-in multi-agent orchestration layer. However, it provides the primitives to build one cleanly:

**Pattern 1: Agent-calls-Agent (hierarchical)**
```python
triage_agent = Agent(model, result_type=TriageResult, deps_type=Deps)
spam_agent = Agent(model, result_type=SpamVerdict, deps_type=Deps)
moderation_agent = Agent(model, result_type=ModerationAction, deps_type=Deps)

@triage_agent.tool
async def escalate_to_spam_check(ctx: RunContext[Deps], message: str) -> str:
    result = await spam_agent.run(message, deps=ctx.deps)
    return result.data.model_dump_json()
```
One agent invokes another as a tool. Simple, explicit, no framework needed.

**Pattern 2: Router/dispatcher pattern**
```python
async def dispatch(message: Message, deps: Deps) -> Action:
    triage = await triage_agent.run(message.text, deps=deps)
    match triage.data.category:
        case "spam":
            return await spam_agent.run(message.text, deps=deps)
        case "harassment":
            return await moderation_agent.run(message.text, deps=deps)
        case _:
            return Action(type="ignore")
```
Pure Python routing. The "orchestration" is just a function.

**Pattern 3: Agent handoff via result types**
PydanticAI's official docs describe a pattern where one agent's result_type is a union that can include "hand off to agent X" variants. The calling code inspects the result and dispatches accordingly. [VERIFY: exact API -- check if `Agent.handoff()` or similar was added post-mid-2025]

### Assessment for Our Use Case

We already use PydanticAI. The multi-agent patterns above are exactly what we do with `AgentCore` + `EscalationService`. The question is whether we need anything more structured.

**Verdict:** PydanticAI is sufficient for multi-agent if you write the orchestration yourself. It deliberately stays out of the orchestration business.

---

## 2. Instructor (Jason Liu)

### What It Is

Instructor is a library by Jason Liu that patches LLM client libraries (OpenAI, Anthropic, etc.) to return Pydantic models. It focuses on structured extraction, retries, and validation.

### Multi-Agent Relevance

Instructor is **not an agent framework**. It is a structured output library. However, it has some relevant patterns:

- **Validation-based retries** -- if the LLM output fails Pydantic validation, it re-prompts with the error. Useful for ensuring agent outputs conform to expected schemas.
- **Streaming + partial validation** -- can validate partial structured outputs during streaming.
- **Function calling abstraction** -- similar to PydanticAI's tool mechanism but more focused on extraction than agentic loops.

Jason Liu has written extensively about "agents" as patterns, not frameworks. His blog posts advocate for:

1. Keeping agents as simple functions
2. Using structured outputs to drive routing
3. Composition over inheritance
4. Explicit state management over hidden graph state

### How It Compares to PydanticAI

PydanticAI subsumes most of Instructor's functionality and adds:
- Built-in tool/function calling
- Dependency injection
- Multi-model support as a first-class concept
- Agent as a reusable, typed callable

If you are already on PydanticAI, Instructor adds nothing. They solve the same problem (structured LLM output) with PydanticAI being more opinionated about the agent pattern.

**Verdict:** Not relevant for our stack. PydanticAI already covers this space.

---

## 3. Workflow Engines: Prefect / Temporal / Dramatiq

### The Idea

Use a general-purpose workflow engine to orchestrate agents instead of an AI-specific framework. Agents become tasks/activities in a workflow.

### Temporal

**What:** A durable execution platform. Workflows are defined as code, and Temporal guarantees they run to completion even across failures, restarts, and deployments.

**Strengths for agents:**
- **Durable state** -- workflow state survives process crashes. Perfect for long-running HITL flows.
- **Timers and signals** -- native support for "wait for human input" (signals), timeouts, and scheduled actions.
- **Retry policies** -- per-activity retry with backoff, ideal for flaky LLM APIs.
- **Visibility** -- built-in UI showing workflow state, history, pending signals.
- **Async Python SDK** -- first-class Python support with async/await.

**How agent orchestration would look:**
```python
@workflow.defn
class ModerationWorkflow:
    @workflow.run
    async def run(self, message: MessageData) -> ModerationResult:
        # Step 1: Triage
        triage = await workflow.execute_activity(
            triage_activity, message, start_to_close_timeout=timedelta(seconds=30)
        )
        # Step 2: Agent analysis
        if triage.needs_agent:
            analysis = await workflow.execute_activity(
                agent_analysis_activity, message, ...
            )
        # Step 3: HITL -- wait for admin decision
        if analysis.confidence < 0.8:
            admin_decision = await workflow.wait_signal("admin_decision")
            return ModerationResult(action=admin_decision.action)
        return ModerationResult(action=analysis.suggested_action)
```

**Downsides:**
- Heavy infrastructure (Temporal server + database + worker processes)
- Learning curve for workflow semantics (determinism constraints)
- Overkill for simple agent patterns

### Prefect

**What:** Python-native workflow orchestration, originally for data pipelines.

**Strengths:** Lighter than Temporal, good Python DX, built-in UI, retry/caching.
**Weaknesses:** Less suited for long-running HITL (designed more for batch/scheduled workflows). The HITL signal pattern is not as clean as Temporal's.

### Dramatiq

**What:** Task queue (like Celery but simpler). Not really a workflow engine.

**Strengths:** Simple, reliable task execution with retries.
**Weaknesses:** No workflow state, no HITL primitives, no durable execution. You would need to build all orchestration logic yourself on top.

### Assessment

Temporal is the most compelling option here if you need durable, long-running workflows with HITL. But it is a significant infrastructure addition. For a Telegram bot that processes messages in near-real-time, the overhead may not be justified unless you have complex multi-step workflows that span hours/days.

**Verdict:** Temporal is worth considering if workflows become complex (multi-day escalations, appeal processes). For current needs, it is overengineered. Dramatiq/Prefect do not add enough over asyncio for agent orchestration.

---

## 4. Asyncio-Native Patterns

### The Core Insight

Python's asyncio already provides the primitives for multi-agent orchestration:
- **Coroutines** -- agents as async functions
- **Tasks** -- concurrent agent execution
- **Queues** -- message passing between agents
- **Events/Conditions** -- synchronization and HITL signaling
- **Semaphores** -- rate limiting LLM calls

### Pattern 1: State Machine

```python
from enum import Enum, auto
from dataclasses import dataclass

class State(Enum):
    TRIAGE = auto()
    ANALYZING = auto()
    AWAITING_HUMAN = auto()
    EXECUTING = auto()
    DONE = auto()

@dataclass
class AgentContext:
    state: State = State.TRIAGE
    message: Message | None = None
    analysis: Analysis | None = None
    human_decision: Decision | None = None

async def run_agent_loop(ctx: AgentContext) -> Result:
    while ctx.state != State.DONE:
        match ctx.state:
            case State.TRIAGE:
                ctx.analysis = await triage_agent.run(ctx.message)
                ctx.state = State.ANALYZING if ctx.analysis.needs_review else State.DONE
            case State.ANALYZING:
                result = await deep_analysis_agent.run(ctx.message, ctx.analysis)
                if result.confidence < THRESHOLD:
                    ctx.state = State.AWAITING_HUMAN
                else:
                    ctx.state = State.EXECUTING
            case State.AWAITING_HUMAN:
                ctx.human_decision = await wait_for_callback(ctx)
                ctx.state = State.EXECUTING
            case State.EXECUTING:
                await execute_action(ctx)
                ctx.state = State.DONE
    return ctx.to_result()
```

**Pros:** Fully explicit, debuggable, no dependencies. States map directly to business logic.
**Cons:** Manual state persistence if you need durability across restarts.

### Pattern 2: Event-Driven with asyncio.Queue

```python
class AgentBus:
    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def publish(self, topic: str, event: Event):
        await self._queues[topic].put(event)

    async def subscribe(self, topic: str) -> AsyncIterator[Event]:
        while True:
            yield await self._queues[topic].get()

# Each agent listens on its topic
async def spam_agent(bus: AgentBus):
    async for event in bus.subscribe("spam.check"):
        result = await analyze_spam(event.message)
        await bus.publish("moderation.action", ActionEvent(result))
```

**Pros:** Decoupled agents, easy to add new agents without modifying existing ones.
**Cons:** Harder to trace execution flow, no built-in persistence.

### Pattern 3: Pipeline with asyncio.TaskGroup (Python 3.11+)

```python
async def parallel_analysis(message: Message) -> CombinedResult:
    async with asyncio.TaskGroup() as tg:
        spam_task = tg.create_task(spam_agent.run(message))
        tone_task = tg.create_task(tone_agent.run(message))
        context_task = tg.create_task(context_agent.run(message))

    return CombinedResult(
        spam=spam_task.result(),
        tone=tone_task.result(),
        context=context_task.result(),
    )
```

### Assessment

This is essentially what we already do. The question is whether to formalize it.

**Verdict:** Asyncio-native patterns are the foundation. The question is how much structure to add on top. A thin state machine layer + event bus is often sufficient.

---

## 5. "Agents Are Just Loops" -- Minimalist Approaches

### Anthropic's Blog Post (January 2025)

Anthropic published "Building effective agents" (anthropic.com/research/building-effective-agents) which argued against complex frameworks. Key points:

1. **Agents are just LLM calls in a loop.** The loop: get input -> call LLM -> parse output -> execute tool -> repeat until done.
2. **Start with the simplest pattern that works.** Most "agents" should be single LLM calls with structured output, not autonomous loops.
3. **Workflow patterns they recommend:**
   - **Prompt chaining** -- sequential LLM calls, each processing the output of the previous
   - **Routing** -- classify input, dispatch to specialized handler
   - **Parallelization** -- fan-out to multiple LLM calls, aggregate results
   - **Orchestrator-workers** -- one LLM decides what to do, dispatches to worker LLMs
   - **Evaluator-optimizer** -- one LLM generates, another evaluates, loop until quality threshold met
4. **Agentic loops only when necessary** -- when the number of steps is not predictable and the LLM needs to decide when to stop.
5. **Keep the agent's "computer interface" simple.** Well-defined tools with clear schemas.

### The "While Loop" Pattern

```python
async def agent_loop(task: str, deps: Deps, max_steps: int = 10) -> Result:
    messages = [SystemMessage(SYSTEM_PROMPT), UserMessage(task)]
    for _ in range(max_steps):
        response = await llm.chat(messages, tools=TOOLS)
        if response.is_final:
            return parse_result(response)
        tool_results = await execute_tools(response.tool_calls, deps)
        messages.extend([response, ToolResultMessage(tool_results)])
    raise MaxStepsExceeded()
```

This is literally what PydanticAI's `agent.run()` does internally. There is no magic.

### Simon Willison's Perspective

Simon Willison has repeatedly argued that most agent frameworks add complexity without proportional value. His recommendation: use a good LLM library (like PydanticAI or raw API clients), write the loop yourself, and keep state management explicit.

### Harrison Chase (LangChain) Acknowledgment

Even Harrison Chase has acknowledged that many LangChain/LangGraph users would be better served by simpler patterns. LangGraph exists for cases where you need complex, stateful, multi-step workflows with persistence, branching, and human-in-the-loop -- not for simple agent loops. [VERIFY: exact quote/context]

**Verdict:** This philosophy validates our current approach. PydanticAI handles the inner loop; we handle the outer orchestration.

---

## 6. Burr -- Hamilton's State Machine Agent Framework

### What It Is

Burr (by DAGWorks, the team behind Hamilton) is a lightweight framework for building stateful applications as state machines. Released ~2024.

### Core Concepts

- **State** -- an immutable dictionary that flows through the application
- **Actions** -- nodes in the state machine that read state and return updated state
- **Transitions** -- conditions that determine which action runs next
- **Application** -- the assembled state machine with persistence, tracking, hooks

```python
@action(reads=["message"], writes=["triage_result"])
async def triage(state: State) -> State:
    result = await triage_agent.run(state["message"])
    return state.update(triage_result=result)

@action(reads=["triage_result", "message"], writes=["moderation_action"])
async def moderate(state: State) -> State:
    result = await moderation_agent.run(state["message"], state["triage_result"])
    return state.update(moderation_action=result)

app = (
    ApplicationBuilder()
    .with_actions(triage=triage, moderate=moderate, wait_human=wait_human)
    .with_transitions(
        ("triage", "moderate", when(needs_moderation=True)),
        ("triage", "done", default),
        ("moderate", "wait_human", when(confidence_low=True)),
        ("moderate", "done", default),
        ("wait_human", "done", default),
    )
    .with_state(message=incoming_message)
    .with_tracker("local", project="moderation")  # built-in UI tracking
    .build()
)
```

### Strengths

- **Explicit state transitions** -- easy to reason about, debug, and test
- **Built-in persistence** -- save/restore state (supports PostgreSQL) [VERIFY: async PostgreSQL support]
- **Built-in tracking UI** -- visual state machine execution viewer
- **Lightweight** -- small library, few dependencies
- **Async support** -- native async actions [VERIFY: full async support maturity]
- **Hooks** -- pre/post action hooks for logging, monitoring
- **Serialization** -- state checkpointing for HITL

### Weaknesses

- **Smaller community** than LangGraph
- **State machine paradigm** -- not all agent patterns map cleanly to state machines
- **Less ecosystem** -- fewer integrations, examples, tutorials

### Assessment for Our Use Case

Burr is interesting because it formalizes exactly what we are building manually: a state machine for moderation workflows. The persistence layer could replace our custom escalation state management. The tracking UI would be a bonus.

**Verdict:** Genuinely worth evaluating. It adds structure without heavy abstraction. The state machine model fits moderation workflows well.

---

## 7. ControlFlow -- Prefect's AI Agent Framework

### What It Is

ControlFlow is a framework by Prefect Labs (the Prefect team) for building AI workflows. It takes a task-centric approach rather than an agent-centric one.

### Core Concepts

- **Task** -- a unit of work with a defined objective and result type
- **Agent** -- an LLM-backed executor that works on tasks
- **Flow** -- a Python function that orchestrates tasks
- **Dependencies** -- tasks can depend on other tasks

```python
import controlflow as cf

@cf.flow
def moderate_message(message: str):
    # Task 1: Triage
    triage = cf.Task(
        "Classify this message",
        result_type=TriageResult,
        context={"message": message}
    )

    # Task 2: Deep analysis (depends on triage)
    analysis = cf.Task(
        "Analyze message for rule violations",
        result_type=AnalysisResult,
        depends_on=[triage],
        agents=[specialized_agent],
    )

    # Task 3: Decision
    decision = cf.Task(
        "Decide moderation action",
        result_type=ModerationAction,
        depends_on=[analysis],
    )

    return decision
```

### Strengths

- **Pythonic** -- flows are just decorated functions, tasks are objects
- **Structured outputs** -- Pydantic result types on tasks
- **Automatic dependency resolution** -- tasks run when their dependencies are met
- **HITL support** -- tasks can be marked as requiring human input [VERIFY: exact HITL API]
- **Prefect integration** -- optionally use Prefect for monitoring, scheduling
- **Multi-agent** -- different agents can work on different tasks within a flow

### Weaknesses

- **Prefect ecosystem dependency** -- while standalone, the full value comes with Prefect
- **Relatively new** -- released mid-2024, still evolving [VERIFY: current maturity]
- **Opinionated about task decomposition** -- may not fit event-driven patterns well
- **Sync-first API** -- async support exists but may not be the primary path [VERIFY]

### Assessment

ControlFlow's task-centric model is interesting but may be awkward for event-driven Telegram bot workflows. Our messages arrive as events, not as pre-planned task graphs. ControlFlow is better suited for batch/planned workflows.

**Verdict:** Interesting design but not a natural fit for real-time event-driven moderation. Better for offline analysis or report generation use cases.

---

## 8. DSPy -- Prompt Optimization vs. Orchestration

### What It Is

DSPy (by Stanford NLP, Omar Khattab) is a framework for **programming** (not prompting) language models. It treats LLM calls as optimizable modules.

### Core Concepts

- **Signatures** -- typed input/output specifications for LLM calls (e.g., `"message -> is_spam: bool, confidence: float"`)
- **Modules** -- composable LLM call units (ChainOfThought, ReAct, etc.)
- **Optimizers** -- automatically tune prompts/few-shot examples to maximize a metric
- **Assertions** -- runtime constraints on LLM outputs

### Relevance to Multi-Agent

DSPy is **not an agent orchestration framework**. It is a prompt optimization framework. However:

- **Module composition** -- you can compose DSPy modules into pipelines, which resembles multi-agent
- **Optimizers** -- can automatically improve agent performance without manual prompt engineering
- **Assertions** -- can enforce output constraints similar to guardrails

```python
class ModerationPipeline(dspy.Module):
    def __init__(self):
        self.triage = dspy.ChainOfThought("message -> category, confidence")
        self.analyze = dspy.ChainOfThought("message, category -> action, reason")

    def forward(self, message):
        triage = self.triage(message=message)
        if triage.confidence > 0.9:
            return self.analyze(message=message, category=triage.category)
        return dspy.Prediction(action="escalate", reason="low confidence")
```

### Strengths

- **Prompt optimization** -- the killer feature. Automatically finds better prompts.
- **Reproducibility** -- compiled programs are deterministic given the same optimizer output.
- **Evaluation-driven** -- forces you to define metrics, which is good practice.

### Weaknesses

- **Not async** -- DSPy is synchronous by default [VERIFY: async support status as of mid-2025]
- **Different mental model** -- treats LLM as a compiled program, not an agent
- **Heavy dependency** -- pulls in a lot of NLP tooling
- **Optimization requires datasets** -- you need labeled examples to optimize

### Assessment

DSPy could be valuable for **optimizing individual agent prompts** within our system, but it is not a replacement for orchestration. It could be used alongside PydanticAI -- use DSPy to find optimal prompts, then hardcode them into PydanticAI agents.

**Verdict:** Complementary tool for prompt optimization, not an orchestration alternative. Consider for improving individual agent quality if prompt engineering becomes a bottleneck.

---

## 9. Mirascope -- Lightweight LLM Toolkit

### What It Is

Mirascope is a lightweight, Pythonic LLM toolkit that emphasizes simplicity and type safety. Similar philosophy to PydanticAI but with some different design choices.

### Core Features

- **Call decorators** -- `@openai.call`, `@anthropic.call` etc. to wrap functions as LLM calls
- **Pydantic integration** -- structured outputs via Pydantic models (like Instructor/PydanticAI)
- **Tool support** -- function-based tools with automatic schema generation
- **Streaming** -- async streaming with typed responses
- **Multi-provider** -- OpenAI, Anthropic, Google, etc.
- **Agents** -- basic agent loop with tools [VERIFY: multi-agent support as of mid-2025]

```python
from mirascope.core import openai

@openai.call("gpt-4o", response_model=TriageResult)
async def triage(message: str) -> str:
    return f"Classify this message: {message}"

@openai.call("gpt-4o", response_model=ModerationAction, tools=[ban_user, mute_user])
async def moderate(message: str, triage: TriageResult) -> str:
    return f"Message: {message}\nTriage: {triage}\nDecide action."
```

### Multi-Agent Patterns

Mirascope's approach to multi-agent is similar to PydanticAI -- it provides the building blocks (typed LLM calls, tools) and you compose them yourself. No built-in orchestration graph.

### How It Compares to PydanticAI

| Feature | PydanticAI | Mirascope |
|---------|-----------|-----------|
| Structured output | Yes | Yes |
| Tools | Yes | Yes |
| Dependency injection | First-class | Manual |
| Async | Full | Full |
| Agent loop | Built-in | Basic |
| Multi-model | Yes | Yes |
| Community size | Larger (Pydantic team) | Smaller |
| Philosophy | Agent-first | Call-first |

### Assessment

Mirascope is a valid alternative to PydanticAI but does not add multi-agent orchestration. Since we are already on PydanticAI, switching would provide no benefit for our orchestration needs.

**Verdict:** Not relevant for us. Comparable to PydanticAI, no orchestration advantage.

---

## 10. FastAPI + Background Tasks as Microservice Agents

### The Pattern

Instead of running multiple agents in one process, run each agent as a separate FastAPI microservice. Orchestration happens via HTTP calls or a message queue.

```
[Telegram Bot] --> [Triage Service] --> [Spam Service]
                                    --> [Moderation Service]
                                    --> [Escalation Service] --> [Admin via Telegram]
```

### Implementation Sketch

```python
# triage_service.py
from fastapi import FastAPI
app = FastAPI()

@app.post("/triage")
async def triage(request: TriageRequest) -> TriageResponse:
    result = await triage_agent.run(request.message)
    return TriageResponse(category=result.category, confidence=result.confidence)

# orchestrator.py
async def process_message(message: Message):
    async with httpx.AsyncClient() as client:
        triage = await client.post("http://triage:8001/triage", json=message.dict())
        if triage.json()["category"] == "spam":
            action = await client.post("http://spam:8002/analyze", json=message.dict())
            ...
```

### When This Makes Sense

- **Different scaling needs** -- spam detection gets 100x more traffic than escalation
- **Different models/hardware** -- one agent needs GPU, others do not
- **Team boundaries** -- different teams own different agents
- **Polyglot** -- some agents in Python, others in different languages
- **Independent deployment** -- update one agent without redeploying everything

### When This Does NOT Make Sense

- **Single team, single process** -- adds network latency and operational complexity for no benefit
- **Tight coupling** -- if agents need to share state frequently, service boundaries create friction
- **Small scale** -- a Telegram bot handling hundreds of messages/day does not need microservices

### Assessment

This is a valid architecture for large-scale systems but massive overkill for our use case. We run one bot process handling one chat cluster. The agents share database connections, configuration, and in-memory state. Splitting them into microservices would add latency, complexity, and operational burden with zero benefit.

**Verdict:** Not appropriate for our scale. Keep everything in-process with asyncio.

---

## 11. Decision Matrix

Evaluation criteria for our specific needs:
- **Python async native** -- must work with asyncio
- **PostgreSQL integration** -- must support our existing DB
- **Telegram bot compatibility** -- event-driven, real-time message processing
- **Long-running workflows** -- escalations that span minutes to hours
- **HITL (Human-in-the-loop)** -- admin callbacks, approval flows
- **Complexity cost** -- learning curve, dependencies, operational overhead
- **Community/maintenance** -- is it actively maintained, can we get help

| Approach | Async | PostgreSQL | Event-Driven | Long-Running | HITL | Complexity | Maturity |
|----------|-------|-----------|-------------|-------------|------|-----------|----------|
| PydanticAI + custom | +++   | +++ (own)  | +++          | ++ (manual)  | ++ (manual) | + (minimal) | +++ |
| Instructor | +++   | N/A       | ++           | +            | +    | + | +++ |
| Temporal | +++   | +++       | ++           | +++          | +++ | --- (heavy infra) | +++ |
| Prefect/ControlFlow | ++    | ++        | +            | ++           | ++   | -- | ++ |
| Dramatiq | ++    | +         | ++           | +            | +    | - | +++ |
| asyncio patterns | +++   | +++ (own)  | +++          | ++ (manual)  | ++ (manual) | + (minimal) | +++ |
| Burr | ++ [VERIFY] | ++ [VERIFY] | ++     | +++          | +++  | - (moderate) | ++ |
| DSPy | + [VERIFY] | N/A       | +            | +            | +    | -- | ++ |
| Mirascope | +++   | N/A       | +++          | ++ (manual)  | ++ (manual) | + | ++ |
| FastAPI microservices | +++ | +++ | +++    | ++           | ++   | --- (ops overhead) | +++ |

**Legend:** +++ excellent, ++ good, + adequate, - cost/limitation, -- significant, --- prohibitive, N/A not applicable

---

## 12. Recommendation

### Can We Stay with PydanticAI + Enhanced Custom Orchestration?

**Yes. Emphatically yes.**

Here is the reasoning:

### What LangGraph gives you (that we might want)

1. **Persistent state across steps** -- we already have this via PostgreSQL
2. **Visual workflow definition** -- nice but not essential for a 3-4 step pipeline
3. **Built-in HITL primitives** -- we already built this with escalation callbacks
4. **Checkpointing/replay** -- useful for debugging, not critical
5. **Branching/conditional logic** -- Python `if/match` statements work fine

### What LangGraph costs you

1. **LangChain dependency** -- large, fast-moving, breaking-changes-prone ecosystem
2. **Graph abstraction** -- forces you to think in nodes and edges even when a simple function would do
3. **Debugging opacity** -- when something goes wrong in the graph, tracing is harder than in plain Python
4. **Lock-in** -- LangGraph state management, message types, and tool definitions are LangGraph-specific
5. **Overhead** -- significant dependency tree, memory footprint, and cognitive load

### The 80/20 Path: PydanticAI + Thin Orchestration Layer

We can get 80%+ of LangGraph's value with minimal additions to our current stack:

**What to build (or adopt):**

1. **Formalize the state machine** -- define states, transitions, and guards explicitly (consider Burr if we want a library, or build a simple `StateMachine` class in ~100 lines)

2. **Add state persistence** -- serialize agent workflow state to PostgreSQL so we can resume after restarts. A simple `workflow_runs` table with JSONB state column.

3. **Structured logging of agent steps** -- log each state transition with input/output for debugging and replay.

4. **Timeout and retry policies** -- wrap agent calls with configurable timeouts and retry logic (we partially have this).

5. **HITL formalization** -- our escalation service already does this. Just make the "wait for human" state explicit in the state machine.

**Estimated effort:** 2-3 days to formalize what we already have into a clean, reusable pattern.

**What NOT to build:**
- Visual graph editor
- Generic workflow engine
- Plugin system for arbitrary agents
- Distributed execution

### If We Outgrow This

If our needs grow significantly (e.g., 10+ specialized agents, complex multi-day workflows, appeal processes with multiple human review stages), then consider:

1. **Burr** -- first choice for adding structure without leaving Python async patterns
2. **Temporal** -- if we need true durable execution with strong consistency guarantees
3. **LangGraph** -- only if we need its specific ecosystem integrations

### Bottom Line

Our current architecture (PydanticAI agent + custom async orchestration + PostgreSQL state + aiogram callbacks for HITL) is already in the sweet spot. The Anthropic "agents are just loops" philosophy validates this approach. The main improvement opportunity is not adding a framework -- it is formalizing and hardening what we already have.

```
Current: PydanticAI + ad-hoc async orchestration
Target:  PydanticAI + explicit state machine + persistent workflow state + structured step logging
Cost:    ~200 lines of orchestration code, 1 new DB table
Benefit: Debuggable, resumable, auditable agent workflows without any new dependencies
```

---

## References

- Anthropic. "Building effective agents." January 2025. https://anthropic.com/research/building-effective-agents
- PydanticAI docs: https://ai.pydantic.dev/
- Burr docs: https://burr.dagworks.io/ [VERIFY: current URL]
- ControlFlow docs: https://controlflow.ai/ [VERIFY: current URL]
- DSPy docs: https://dspy-docs.vercel.app/ [VERIFY: current URL]
- Mirascope docs: https://mirascope.io/ [VERIFY: current URL]
- Temporal Python SDK: https://docs.temporal.io/develop/python
- Jason Liu (Instructor): https://python.useinstructor.com/
- Simon Willison's blog: https://simonwillison.net/
