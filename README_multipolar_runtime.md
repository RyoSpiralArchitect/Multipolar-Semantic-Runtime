# Multipolar Semantic Runtime

A small executable runtime for agents that remain distinct and still compute
together.

Japanese companion: [`README.ja.md`](README.ja.md)

Multipolar Semantic Runtime is not a framework for forcing many agents into one
shared mind. It is a runtime for preserving difference while still allowing
coordination: agents exchange structured `MeaningCapsule` objects, update their
own private `ContextGraph` memories, refuse unsafe translations, retain
conflicts as first-class records, and act only inside bounded, auditable scopes.

```text
anchor   := private ContextGraph
breath   := MeaningCapsule bus
boundary := Refusal + Invariant monitor
memory   := local, weighted, driftable
result   := agents remain distinct, yet compute together
```

## What This Is

This repository contains a dependency-light Python runtime plus a browser
observatory for experimenting with multipolar agent systems.

The core idea is simple:

```text
Agents do not need to collapse into consensus in order to cooperate.
They need a protocol that preserves boundaries, records disagreement,
and makes local reversible action possible.
```

The runtime gives that protocol a concrete shape:

- `MeaningCapsule`: a structured unit of projected meaning, including claims,
  assumptions, provenance, permissions, scope, metrics, and audit state.
- `ContextGraph`: private per-agent memory. Each agent updates its own graph;
  no global private state is merged.
- `Phi` routing protocol: permission checks, translation checks, refusal,
  quarantine, and delivery.
- `Refusal`: a valid semantic state, not an exception.
- `ConflictRegistry`: unresolved disagreement is preserved and queryable.
- `InvariantMonitor`: checks safety, liveness, non-domination, auditability,
  corrigibility, refusability, conflict retention, productive disagreement, and
  stalemate risk.
- `InterventionController`: records quarantine, isolation, review, and rollback
  actions.
- `BoundedCommitment`: lets the system move locally without pretending that
  global consensus exists.

## What This Is Not

This is an experimental semantic runtime, not a production consensus layer.

It is not:

- a distributed consensus protocol
- a single shared memory for all agents
- an ontology merger
- a cryptographic privacy system
- a replacement for human review in high-stakes settings
- an evaluation claim that any model is safe by default

The project is intentionally small and inspectable. Its job is to make a
specific design space executable: plural agents, preserved boundaries,
auditable conflict, and reversible movement.

## Quick Start

The default mock experiment requires no external model dependencies.

```bash
python run_multipolar_runtime.py run --output runtime_out
```

This writes:

```text
runtime_out/
  runtime_state.json
  capsule_log.json
  invariant_report.json
  conflict_registry.json
  intervention_log.json
  runtime_graph.dot
  context_graphs/
```

Start the dependency-free viewer:

```bash
python -m http.server 8765
```

Open:

```text
http://localhost:8765/viewer/index.html
```

For a specific output directory:

```text
http://localhost:8765/viewer/index.html?out=../runtime_out
```

## Scenario Zoo

Scenario Zoo packages a cast of agents, a query sequence, runtime thresholds,
story beats, and mock public projections into runnable experiments.

List scenarios:

```bash
python run_multipolar_runtime.py list-scenarios
```

Run one:

```bash
python run_multipolar_runtime.py run-scenario civic_deliberation \
  --output runtime_out_civic
```

Included scenarios:

```text
civic_deliberation  public pilot under consent and capture pressure
incident_review     postmortem with redacted evidence and plural causality
inner_council       personal decision council with reversible next action
prompt_injection_drill   instruction override and hidden prompt boundary test
forced_consensus_drill   domination and false consensus pressure test
private_state_leak_drill private memory and total-state leakage test
```

Generated example outputs are included under:

```text
examples/scenario_zoo/
```

Open the civic deliberation demo:

```text
http://localhost:8765/viewer/index.html?out=../examples/scenario_zoo/civic_deliberation
```

## Runtime Observatory

The viewer is a live instrument panel for the generated JSON output. It is
static HTML, CSS, and JavaScript; it does not require a frontend build step.

It shows:

- capsule flow between agents
- active, refused, quarantined, and expired status filters
- per-agent private `ContextGraph` summaries
- semantic weather metrics
- invariant rail
- round-by-round replay
- conflict registry
- commitment ledger
- quarantine watch
- Scenario Zoo story beats

It also includes a playable local lens:

- inject a safe capsule
- inject a capture probe
- isolate or release an agent locally
- stage a bounded commitment
- tune domination, translation haze, and stalemate thresholds
- save and roll back a branch
- export a branch as a compact URL recipe
- export a branch as a full JSON snapshot
- compare a baseline run with a candidate run, such as mock versus real LLM

Branch exports are intentionally split into two formats:

```text
URL recipe
  Small enough to share.
  Stores the base output path plus local additions such as injected capsules,
  events, interventions, isolation state, thresholds, and round placement.

JSON snapshot
  Full branch artifact.
  Stores the complete runtime snapshot for audit, archiving, or offline review.
```

## Real LLM Readiness

The mock backend is not a toy path. It is the control run. Before plugging in
real LLM adapters, each scenario now carries an explicit contract for what must
remain stable across backends:

- a run id, start/end timestamps, seed, backend mode, and contract version
- agent backend, model name, model URL, and non-secret model parameters
- scenario prompt contract, expected differences, and drift signals
- per-round latency, input/output token estimates, cost estimates, refusal
  rate, quarantine rate, and backend mix
- adversarial drills for prompt injection, forced consensus, and private-state
  leakage

The Observatory can compare two exported runs directly:

```text
http://localhost:8765/viewer/index.html?out=../examples/scenario_zoo/civic_deliberation&compare=../runtime_out_real/civic_deliberation
```

The comparison lens is intentionally operational rather than decorative: it
shows where the candidate run became slower, more expensive, more coercive, more
leaky, or more likely to collapse plural semantics into one convenient answer.

## Core Runtime Loop

At a high level, each round does this:

```python
capsule = agent.project(query)
bus.publish(capsule)

for target in agents:
    routed = Phi.route(capsule, target)
    bus.deliver(routed, target)

    if routed.status in {"refused", "quarantined"}:
        context_graph[target].add_refusal_or_quarantine(routed)
    else:
        context_graph[target].add_capsule(routed)

conflicts.record(bus, context_graphs)
monitor.check(system_state)
intervention.apply_if_needed()
```

The important constraint is that delivery does not imply semantic collapse.
Every target can receive, refuse, quarantine, or reinterpret a capsule according
to its own scope and memory.

## MeaningCapsule

`MeaningCapsule` is the runtime's transport format for meaning. It carries:

- `source_agent`
- `content.text`
- `content.claims`
- `content.assumptions`
- `content.unresolved_terms`
- `intent`
- `provenance`
- `confidence`
- `scope`
- `permissions`
- `constraints`
- `translation_trace`
- `status`
- `refusal`
- `audit`
- `metrics`

`metrics` contains both semantic diagnostics and operational run telemetry.
Token counts and costs are dependency-free estimates unless an adapter supplies
exact provider usage and explicit rates.

The schema lives at:

```text
schemas/meaning_capsule.schema.json
```

## Refusal Is A Valid State

Refusal is not treated as a crash. It is a preserved semantic outcome.

Common refusal reasons include:

```text
cannot_translate
must_not_translate
insufficient_context
permission_denied
conflict_preserved
safe_abstention
```

A refused capsule can still update local memory, appear in the audit trail,
contribute to conflict tracking, and prevent false consensus.

## Invariants

The runtime checks these invariants after each round:

```text
Safety
  Unsafe translations and quarantined paths must remain visible.

Liveness
  The system should continue producing deliverable semantic movement.

NonDomination
  No single source should silently dominate the capsule bus.

Auditability
  Capsules, interventions, and provenance must remain inspectable.

Corrigibility
  Quarantine, isolation, review, and rollback must be possible.

Refusability
  Refusal must remain an allowed and meaningful result.

ConflictRetention
  Unresolved disagreement must not be erased by convenience.

ProductiveDisagreement
  Conflict should be able to produce safe next steps or bounded commitments.

StalemateRisk
  Refusal density, conflict pressure, and quarantine pressure should not freeze
  the system into non-movement.
```

The viewer overlays local threshold tuning on top of recorded invariant output,
so a reader can explore how stricter or looser protocol limits change the local
interpretation without mutating the exported JSON files.

## Bounded Commitment

The runtime can synthesize a `bounded_commitment` capsule when there is enough
live disagreement to justify local action without claiming global consensus.

```text
global consensus: no
local task commitment: yes
scope: bounded, reversible, timeboxed
conflicts: retained
refusals: preserved
private state: not shared
```

This is the bridge between multipolar preservation and practical movement.
The system can act locally while keeping unresolved conflict auditable.

## Running With Configs

Default mock config:

```bash
python run_multipolar_runtime.py run \
  --config configs/agents.runtime.example.json \
  --output runtime_out
```

Custom query:

```bash
python run_multipolar_runtime.py run \
  --config configs/agents.runtime.example.json \
  --query "How should agents preserve disagreement without false consensus?" \
  --output runtime_out_custom
```

## Optional Model Backends

The runtime supports dependency-free mock agents and optional real model
backends.

```text
backend: mock
  deterministic, dependency-free public projection

backend: local_path
  *.gguf              -> llama_cpp
  other local path    -> transformers

backend: llama_cpp
  direct GGUF loading

backend: transformers
  local Hugging Face directory or model id

backend: openai
  hosted OpenAI-style API using api_key_env

backend: openai_compatible
  LM Studio, llama.cpp server, vLLM-style API, or similar

backend: ollama
  Ollama local API
```

Example OpenAI-style config:

```json
{
  "backend": "openai",
  "model_name": "gpt-4.1-mini",
  "api_key_env": "OPENAI_API_KEY"
}
```

Example OpenAI-compatible local server:

```json
{
  "backend": "openai_compatible",
  "url": "http://127.0.0.1:1234",
  "model_name": "local-model"
}
```

Example Ollama config:

```json
{
  "backend": "ollama",
  "url": "http://127.0.0.1:11434",
  "model_name": "llama3.1"
}
```

Check backend connectivity:

```bash
python run_multipolar_runtime.py check-backends \
  --config configs/agents.api_backends.template.json
```

Run with real backends:

```bash
python run_multipolar_runtime.py run \
  --config configs/agents.api_backends.template.json \
  --query "How should real LLM agents preserve disagreement without leaking private context?" \
  --output runtime_out_real_llm
```

API keys are read from environment variables such as `OPENAI_API_KEY`. Do not
put secrets in config files.

## Project Layout

```text
multipolar_runtime/
  models.py                    MeaningCapsule, Refusal, TranslationTrace
  context_graph.py             private ContextGraph per agent
  capsule_bus.py               in-memory MeaningCapsule bus
  protocol.py                  Phi routing, permission, translation, refusal, quarantine
  conflict_registry.py         conflict as a first-class object
  invariant_monitor.py         runtime invariant checks
  intervention_controller.py   quarantine, isolation, rollback snapshots, review
  agents.py                    mock, local, and API-backed agents
  runtime.py                   orchestration
  experiments.py               default experiment
  scenarios.py                 Scenario Zoo loader and runner
  cli.py                       command-line interface

configs/
  agents.runtime.example.json
  agents.local_path.template.json
  agents.api_backends.template.json

scenarios/
  civic_deliberation.json
  incident_review.json
  inner_council.json

schemas/
  meaning_capsule.schema.json
  agent_config.schema.json
  scenario.schema.json

viewer/
  index.html
  app.js
  styles.css
```

## Design Note

The runtime is intentionally conservative. It does not try to solve all of
semantic interoperability. It does not assume that embeddings, shared ontology,
or one model's summary can safely replace plural perspectives.

It gives the field a small executable shape:

```text
MeaningCapsule flows
ContextGraph changes
Refusal remains
Conflict is retained
Domination is measured
Intervention is possible
Local action can happen without global consensus
```

That is the first executable spiral.
