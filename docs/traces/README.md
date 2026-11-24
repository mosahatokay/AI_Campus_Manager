# CampusAI — Agent Traces for Milestone 1

The two JSON trace files are **real executions of the Python agent loop using synthetic test data**, but the model decisions are authored in advance by `ScriptedModel`. They are **not evidence of live LLM decision quality**.

Run locally or in a clean Colab clone:

```bash
python -m src.trace_examples
python -m pytest -q
```

- `success.json`: a scripted `get_availability` request succeeds on the first tool execution, and the agent returns a final answer.
- `transient_failure.json`: the mocked backend rejects the first three attempts, exhausting the two allowed read retries. The tool returns `service_unavailable` with `retryable=true`. The agent receives this observation and returns an explanatory answer. No booking is written.

Trace structure: `scripted_decisions` shows the model-test-double instructions; `timeline` tracks decision -> tool -> observation -> final answer; `tool_trace` records execution attempt counts and status; `agent_audit` records the agent-level decisions. Latencies vary on every replay and are **not** performance benchmarks.

The traces contain no SQL Server data, personal data, credentials, or paid API calls. The program writes only under `docs/traces/`.
