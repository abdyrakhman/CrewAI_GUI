# CrewAI 1.x API reference (for a GUI backend)

Verified against **crewai 1.15.45** (`crewai.__version__ == "1.15.45"`), Nov 2026.
Sources: docs.crewai.com was unreachable from this host, so every claim comes from the identical MDX sources in
the repo — `raw.githubusercontent.com/crewAIInc/crewAI/main/docs/v1.15.45/en/...` — plus library source
`lib/crewai/src/crewai/...`. Unverified items are marked **UNVERIFIED**.

## 1. Install

```shell
pip install crewai            # core
pip install 'crewai[tools]'   # + crewai-tools (SerperDevTool, FileReadTool, ...)
uv tool install crewai        # CLI: crewai run / train / test / replay / flow plot
```
- Python **`>=3.10, <3.14`** (`lib/crewai/pyproject.toml`). `tools` extra pins `crewai-tools==1.15.45`.
- Extras: `litellm` (all non-native providers), `openai`, `anthropic`, `google-genai`, `azure-ai-inference`,
  `bedrock`, `chromadb`, `qdrant`, `file-processing`, `spreadsheets`, `pdf`, `embeddings`, `a2a`, `mem0`,
  `docling`, `pandas`.

## 2. `Agent` — `from crewai import Agent`

```python
agent = Agent(
    role="Senior Data Scientist",                        # required
    goal="Analyze and interpret complex datasets ...",   # required
    backstory="With over 10 years of experience ...",    # required
    llm="gpt-6-luna",            # str OR LLM; default = OPENAI_MODEL_NAME or "gpt-6-luna"
    function_calling_llm=None,   # Optional[Any]; overrides crew LLM for tool calling
    verbose=False,               # bool (ints no longer mean log levels)
    allow_delegation=False, max_iter=20, max_rpm=None, max_execution_time=None, max_retry_limit=2,
    cache=True, respect_context_window=True, use_better_compaction=True,
    allow_code_execution=False, code_execution_mode="safe",   # both DEPRECATED
    use_system_prompt=True, multimodal=False, inject_date=False, date_format="%Y-%m-%d",
    reasoning=False, max_reasoning_attempts=None,             # None = retry until ready
    tools=[SerperDevTool()],     # List[BaseTool] = []
    knowledge_sources=None, embedder=None,
    system_template=None, prompt_template=None, response_template=None,   # templates, not tools
    step_callback=None,          # called after each agent step
    tool_failure_policy=None,    # ToolFailurePolicy; inherits (effective default "warn")
)
```
- `max_iter`: `20` in `concepts/agents`, `25` in `learn/customizing-agents` — docs disagree, set explicitly.
- `llm` takes `"openai/gpt-4o"`-style strings **or** an `LLM(...)` object. `max_rpm=None` = unlimited;
  crew-level `max_rpm` overrides the agent's.
- `memory=True` appears in official Agent examples but is **absent from the 1.15.45 attribute table**.
- Standalone: `agent.kickoff(messages, response_format=None)` → `LiteAgentOutput` (`.raw`, `.pydantic`,
  `.agent_role`, `.usage_metrics`); `agent.kickoff_async(...)`; `agent.handle_turn(...)` (conversational, experimental).
- 1.15.29 removed `executor_class=CrewAgentExecutor`; only `from crewai.agents import AgentExecutor` exists.

## 3. `Task` — `from crewai import Task`

```python
task = Task(
    description="Research {topic} ...",        # required
    expected_output="A bullet list of ...",    # required
    agent=researcher,              # Optional[BaseAgent]; None under hierarchical
    tools=[search_tool],           # overrides the agent's tools for this task only
    context=[research_task],       # List[Task] -> waits for + injects their outputs
    async_execution=False, human_input=False, markdown=False,
    output_file="output/report.md", create_directory=True,   # False + missing dir -> RuntimeError
    output_json=None, output_pydantic=None,   # pydantic CLASS (not instance); mutually exclusive
    callback=callback_function,    # callback(output: TaskOutput)
    guardrail=None,                # Callable | str (str -> LLMGuardrail)
    guardrails=None,               # List[Callable | str]; takes precedence over guardrail
    guardrail_max_retries=3,
    name="research_task", tool_failure_policy=None,
)
```
- Guardrail contract: `def g(result: TaskOutput) -> tuple[bool, Any]` → `(True, value)` / `(False, "feedback")`;
  on failure the feedback goes back to the agent, retried up to `guardrail_max_retries`.
- `Task.max_retries` is **deprecated** → `guardrail_max_retries`.
- `task.output` → `TaskOutput{description, summary, raw, pydantic, json_dict, agent, output_format, messages,
  tool_failures}`.
- With tools + `output_*`: the schema rides in the prompt; if the final answer doesn't fit, one extra
  schema-only, no-tools call is made over the same conversation and `raw` becomes that JSON.

## 4. `Crew` — `from crewai import Crew, Process`

```python
crew = Crew(
    agents=[researcher, writer],         # required
    tasks=[research_task, write_task],   # required
    process=Process.sequential,          # default; else Process.hierarchical
    verbose=False, memory=False, cache=True, max_rpm=None,       # max_rpm overrides every agent
    manager_llm="gpt-4o", manager_agent=None,   # hierarchical: ONE of these is required
    function_calling_llm=None, planning=False, planning_llm=None,
    output_log_file=None,                # True -> logs.txt; "x.txt"/"x.json" by suffix
    stream=False,                        # -> kickoff() returns CrewStreamingOutput
    embedder={"provider": "openai"}, step_callback=None, task_callback=None,
    before_kickoff_callbacks=[],         # each receives & may modify the inputs dict
    after_kickoff_callbacks=[],          # each receives & may modify the CrewOutput
    knowledge_sources=None, share_crew=False, config=None, prompt_file=None,
    chat_llm=None, tracing=None, skills=None, security_config=SecurityConfig(),
    checkpoint=None,                     # True | CheckpointConfig | False | None
)
```
`Process` is an `Enum`: `Process.sequential`, `Process.hierarchical`. Hierarchical without `manager_llm`/
`manager_agent` raises at kickoff validation; the manager allocates tasks (none pre-assigned).

```python
result  = crew.kickoff()                                  # -> CrewOutput
result  = crew.kickoff(inputs={"topic": "AI"})
result  = crew.kickoff(inputs={"topic": "AI"}, input_files={"chart": ImageFile(source="c.png")})
results = crew.kickoff_for_each(inputs=[{"topic": "a"}, {"topic": "b"}])   # List[CrewOutput]
await crew.akickoff(inputs={...})                 # native async
await crew.akickoff_for_each(inputs=[...])
await crew.kickoff_async(inputs={...})            # thread-based
await crew.kickoff_for_each_async(inputs=[...])
crew.train(n_iterations=2, inputs={"topic": "x"}, filename="your_model.pkl")
crew.test(n_iterations=5, eval_llm="openai/gpt-4o", inputs={...})
crew = Crew.from_checkpoint(".checkpoints/latest.json"); crew.kickoff()   # resume
```
`CrewOutput`: `raw: str`, `pydantic: Optional[BaseModel]`, `json_dict: Optional[Dict[str, Any]]`,
`tasks_output: List[TaskOutput]`, `token_usage: Dict[str, Any]` (`total_tokens == prompt_tokens +
completion_tokens`), `tool_failures` / `has_tool_failures`. Methods: `json`, `to_dict()`, `result["field"]`,
`str(result)` (pydantic → json → raw). Post-run: `crew.usage_metrics`. `train()` needs a positive
`n_iterations` and a `filename` ending `.pkl`, and is interactive (tasks get `human_input=True`).

## 5. `LLM` and model strings

```python
from crewai import LLM
llm = LLM(model="openai/gpt-4o", temperature=0.7, max_tokens=4000,
          base_url="https://api.openai.com/v1", api_key="sk-...")
```
Format is **`provider/model-id`** — "Always include the provider prefix": `openai/gpt-4o`,
`anthropic/claude-sonnet-4-6`, `gemini/gemini-3.6-flash`, `azure/gpt-4o`, `ollama/llama3:70b`,
`openrouter/deepseek/deepseek-r1`, `groq/...`, `bedrock/...`, `snowflake/...`.
Documented params: `model, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, stop, base_url,
api_key, timeout, max_retries, response_format (pydantic class), stream, api="responses"|"completions",
organization, project, reasoning_effort, max_completion_tokens, stop_sequences, seed, thinking, safety_settings,
drop_params, additional_drop_params, context_window_size, interceptor, custom_openai, endpoint, api_version,
max_output_tokens`. Methods: `call(messages)`, `await acall(...)`, `get_context_window_size()`,
`get_token_usage_summary()`.

```python
LLM(model="ollama/llama3.2", base_url="http://localhost:11434")
LLM(model="openrouter/deepseek/deepseek-r1", base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)
LLM(model="openai/local-model", base_url="http://localhost:1234/v1", api_key="not-needed")  # LM Studio/vLLM
```
Env vars: `MODEL` (project default, e.g. `openai/gpt-5.6-terra`); `OPENAI_API_KEY`; `OPENAI_MODEL_NAME`
(agent default when `llm` is omitted, itself defaulting to `"gpt-6-luna"`); `OPENAI_BASE_URL` (native OpenAI);
`OPENAI_API_BASE` (base URL on the `OPENAI_MODEL_NAME` OpenAI-compatible path); credentials
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `AZURE_API_KEY`/`AZURE_ENDPOINT`/`AZURE_API_VERSION`,
`AWS_*`, `SNOWFLAKE_*`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `SERPER_API_KEY`, `HF_TOKEN`, `WATSONX_*`,
`DEEPINFRA_*`; plus `CREWAI_TRAINED_AGENTS_FILE` and `CREWAI_DMN`.

## 6. Events / streaming (GUI-critical)

Import surface is **`crewai.events`**; the 0.x `crewai.utilities.events` path no longer exists on `main`.

```python
from crewai.events import crewai_event_bus, BaseEventListener, CrewKickoffStartedEvent
from crewai.events.event_bus import crewai_event_bus          # equivalent

class MyListener(BaseEventListener):          # must be instantiated and kept alive
    def setup_listeners(self, crewai_event_bus):
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_started(source, event): print(event.crew_name, event.inputs)

@crewai_event_bus.on(TaskStartedEvent)        # module-level decorator
def on_task(source, event): print(event.task_name, event.agent_role)

with crewai_event_bus.scoped_handlers():      # auto-removed on exit
    @crewai_event_bus.on(LLMStreamChunkEvent)
    def tmp(source, event): print(event.chunk)
```
Handler signature is always `(source, event)`.

`BaseEvent` fields on **every** event: `timestamp`, `type`, `event_id`, `parent_event_id`, `previous_event_id`,
`triggered_by_event_id`, `started_event_id`, `emission_sequence`, `task_id`, `task_name`, `agent_id`,
`agent_role`, `source_fingerprint`, `source_type`, `fingerprint_metadata`.

Exact names in `crewai.events.__all__` (1.15.45), by family:
- **Crew**: `CrewKickoffStartedEvent{crew_name, crew, inputs}`, `CrewKickoffCompletedEvent{output, total_tokens}`,
  `CrewKickoffFailedEvent{error}`, `CrewTestStartedEvent{n_iterations, eval_llm, inputs}`, `CrewTestCompletedEvent`,
  `CrewTestFailedEvent{error}`, `CrewTestResultEvent{quality, execution_duration, model}`, `CrewTrainStartedEvent`,
  `CrewTrainCompletedEvent`, `CrewTrainFailedEvent`.
- **Agent**: `AgentExecutionStartedEvent`, `AgentExecutionCompletedEvent{output}`, `AgentExecutionErrorEvent`,
  `LiteAgentExecution{Started,Completed,Error}Event`, `AgentEvaluation{Started,Completed,Failed}Event`,
  `AgentReasoning{Started,Completed,Failed}Event`, `AgentLogs{Started,Execution}Event`.
- **Task**: `TaskStartedEvent{context, task}`, `TaskCompletedEvent{output: TaskOutput, task}`,
  `TaskFailedEvent{error, error_type}`, `TaskEvaluationEvent`.
- **LLM**: `LLMCallStartedEvent{messages, tools, temperature, max_tokens, stream, ...}`,
  `LLMCallCompletedEvent{response, call_type, usage, finish_reason, response_id}`, `LLMCallFailedEvent{error}`,
  **`LLMStreamChunkEvent{chunk, tool_call, call_type, response_id, model, call_id}`**,
  `LLMThinkingChunkEvent{chunk, response_id}`, `ContextWindowSummarization{Started,Completed,Failed}Event`.
  `LLMEventBase` auto-fills `task_id`/`task_name`/`agent_id`/`agent_role`, so each chunk routes to a UI pane.
- **Tool**: `ToolUsageStartedEvent`, `ToolUsageFinishedEvent` (carries `failure`), `ToolUsageErrorEvent`,
  `ToolExecutionErrorEvent`, `ToolSelectionErrorEvent`, `ToolValidateInputErrorEvent`,
  `ToolFailureDetectedEvent{tool_name, failure, policy}`.
- **Other**: `Flow{Created,Started,Finished,Failed,Plot}Event`, `MethodExecution{Started,Finished,Failed}Event`,
  `HumanFeedback{Requested,Received}Event`, `ConversationTurn*`, `Memory{Query,Save,Retrieval}*`,
  `Knowledge{Query,Retrieval}*`, `MCP{Connection,ToolExecution,ConfigFetch}*`, `LLMGuardrail{Started,Completed}`,
  `Checkpoint*`, `Skill*`, `PlanStep*`, `ArtifactCreatedEvent`, `Depends`, `CircularDependencyError`.
- Docs also list `FlowInput{Requested,Received}Event`, `FlowPausedEvent`, `MethodExecutionPausedEvent`,
  `StepObservation*Event`, `PlanRefinementEvent`, `PlanReplanTriggeredEvent`, `GoalAchievedEarlyEvent`,
  `A2A*Event` — **not** in `crewai.events.__all__` in 1.15.45 (**UNVERIFIED** import path).

## 7. Tools

```python
from crewai_tools import (DirectoryReadTool, FileReadTool, SerperDevTool,
                          ScrapeWebsiteTool, WebsiteSearchTool, RagTool)
docs_tool = DirectoryReadTool(directory='./blog-posts')
file_tool = FileReadTool()
search    = SerperDevTool()      # needs SERPER_API_KEY
scraper   = ScrapeWebsiteTool()
```
Custom tool — canonical import is `crewai.tools` (**not** `crewai_tools`):
```python
from crewai.tools import tool, BaseTool

@tool("Name of my tool")
def my_tool(question: str) -> str:
    """Clear description for what this tool is useful for, your agent will need this information to use it."""
    return "Result from your custom tool"
my_tool.cache_function = lambda args, result: True

class MyCustomTool(BaseTool):
    name: str = "Name of my tool"
    description: str = "What this tool does."
    args_schema: type[BaseModel] = MyToolInput      # pydantic input model
    def _run(self, argument: str) -> str: return "..."
```
- Async: `@tool` on an `async def`, or `async def _run`/`_arun` on a `BaseTool`.
- Typed output: return a pydantic model, or `@tool("X", result_schema=Model)`; override
  `format_output_for_agent(raw)` to change only what the agent sees.
- Failures: return `ToolFailure(message=..., code=..., retryable=...)` (`crewai.tools.tool_failure`); policy
  `ToolFailurePolicy.IGNORE|WARN|RAISE`, precedence tool → task → agent → crew → `warn`.

## 8. Flows (brief)

```python
from crewai.flow.flow import Flow, start, listen, router, or_, and_   # all re-exported by crewai.flow

class MyFlow(Flow[MyState]):
    @start()
    def begin(self): return self.state.topic          # state via self.state

    @listen(begin)
    def next_step(self, result): ...

    @router(next_step)
    def route(self): return "path_a"                  # or_("a","b") / and_("a","b") to combine

flow = MyFlow(); out = flow.kickoff(); flow.plot("flow_diagram")   # -> flow_diagram.html
flow.kickoff(input_files={"image": ImageFile(source="data.png")})
```
Also in `crewai.flow`: `persist`, `human_feedback`, `flow_config`, `InputProvider`, `ConversationalConfig`,
`ChatState`, `visualize_flow_structure`.

## 9. Streaming + documented limits

Two independent mechanisms, both current: (1) `Crew(stream=True)` → `kickoff()` returns an iterable
**`CrewStreamingOutput`**; (2) the event bus (`LLMStreamChunkEvent`, `Task*`, `AgentExecution*`), which works
**without** `stream=True` and carries `task_id`/`agent_role` — the better choice for per-task GUI panes.

```python
streaming = crew.kickoff(inputs={"topic": "AI"})     # CrewStreamingOutput
for chunk in streaming:                              # `async for` under akickoff/kickoff_async
    print(chunk.task_name, chunk.task_index, chunk.agent_role, chunk.chunk_type, chunk.content)
    if chunk.tool_call: print(chunk.tool_call.tool_name, chunk.tool_call.arguments)
result = streaming.result                            # CrewOutput — valid only after full iteration
```
`CrewStreamingOutput`: `.result`, `.results`, `.chunks`, `.is_completed`, `.is_cancelled`, `.get_full_text()`,
`.close()`/`await .aclose()` (idempotent), async context manager. `chunk.chunk_type` compares against
`StreamChunkType.TEXT` / `.TOOL_CALL` (`from crewai.types.streaming import StreamChunkType`).

Limits/gotchas: consume **all** chunks before `.result`; `stream=True` enables LLM streaming for **all** agents;
sync `kickoff_for_each()` returns a **list** of outputs while `kickoff_for_each_async()` returns one object with
`.results`; no documented chunk-rate cap. Context budget is **85%** of the catalogued window; unknown models
default to **8,192** tokens (→ 6,963 usable) for OpenAI/Azure/Bedrock/OpenAI-compatible/LiteLLM and **4,096** for a
custom `BaseLLM` without `get_context_window_size()` (override `LLM(context_window_size=N)`). Tool results over
**25%** of that window are deferred to a temp file (`use_better_compaction=False` disables). Same tool + same args
+ same result **5×** aborts the task with `ToolExecutionFailedError` (fixed; `max_retry_limit` won't retry it).
`respect_context_window=False` + overflow raises `SystemExit` (not an `Exception`).

## 10. 0.x → 1.x breaking changes (verified)

- **Events moved**: `crewai.utilities.events` is gone on `main`; use `crewai.events`.
- **Tools imports**: `from crewai.tools import BaseTool, tool` is canonical; `from crewai_tools import BaseTool` and
  `from crewai.agents.tools import tool` are old. `AgentFinish` and other internal-agent symbols left the public
  surface — use event listeners or `Task` callbacks.
- **`CrewAgentExecutor` removed (1.15.29)**; only `AgentExecutor`. `crewai.agents.crew_agent_executor` and
  `crewai.experimental.*` import paths are gone; `executor_class="CrewAgentExecutor"` fails validation.
- **Code execution removed**: `allow_code_execution`/`code_execution_mode` deprecated, `CodeInterpreterTool` dropped
  from `crewai-tools` — use E2B/Modal.
- **`Task.max_retries` deprecated** → `guardrail_max_retries`.
- **`verbose` is a plain `bool`**; ints no longer toggle log levels.
- **`Process.hierarchical` needs `manager_llm=` or `manager_agent=`**; tasks are manager-allocated.
- **`max_iter` default shifted across releases** (docs say both 20 and 25) — set it explicitly.
- **`output_pydantic`/`output_json` take the class**, not an instance.
- **`memory=True` + non-default embedder** needs an `embedder` dict; default OpenAI `text-embedding-3-large` is
  3072-dim and can clash with old 1536-dim stores (`crewai reset-memories -m`).
- 1.15.29 behaviour: deferred oversized tool results, proactive context summarization, repeated-call abort.
- `crewai test` uses `--n-iterations`/`-n`; `--n_iterations` is deprecated but accepted.
- 1.0.0 release notes (2025-10-20) carry **no** explicit breaking-change list; the above is reconstructed from
  `guides/migration/upgrading-crewai` plus the per-concept pages. No official 0.x→1.x migration page was found.

## 11. UNVERIFIED / open

1. Any deprecation shim for `crewai.utilities.events` in the installed 1.15.45 wheel (path absent on `main`).
2. `max_iter` default: 20 vs 25 (docs contradict). 3. `Agent(memory=True)`: used in docs, absent from the table.
4. Exact `Crew.kickoff` signature (`inputs: dict | None`, `input_files: dict[str, FileInput] | None`) — call sites
   only. 5. Import path for `FlowInput*`, `FlowPaused`, `StepObservation*`, `PlanRefinement`, `GoalAchievedEarly`,
   `A2A*`. 6. `CREWAI_*` vars beyond `CREWAI_TRAINED_AGENTS_FILE`/`CREWAI_DMN`. 7. Non-interactive `crew.train()`.
