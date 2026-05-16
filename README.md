# Multipolar Semantic Runtime

`MeaningCapsule` / `OpenAPI` の次の螺旋として作った、最小の実行時システムです。

これは「複数主体がひとつになる」ための実装ではありません。  
**ひとつになれない主体たちが、ひとつにならないまま MeaningCapsule を交換し、ContextGraph を変化させ、Refusal と Invariant を保存する**ための小さなランタイムです。

```text
anchor   := private ContextGraph
breath   := MeaningCapsule Bus
boundary := Refusal + Invariant Monitor
memory   := local, weighted, driftable
result   := agents remain distinct ∴ yet compute together
```

## What is included

```text
multipolar_runtime/
  models.py                    # MeaningCapsule, Refusal, TranslationTrace
  context_graph.py             # private ContextGraph per agent
  capsule_bus.py               # in-memory MeaningCapsule bus
  protocol.py                  # Φ: permission, translation, refusal, quarantine
  conflict_registry.py          # conflict as first-class object
  invariant_monitor.py          # Safety / Liveness / NonDomination / Auditability / Corrigibility / Refusability
  intervention_controller.py    # quarantine, isolation, rollback snapshots, review
  agents.py                    # mock/local/API-backed agent runtime
  runtime.py                   # orchestration
  experiments.py               # Experiment 001
  cli.py                       # command-line runner

configs/
  agents.runtime.example.json        # mock 5-agent experiment
  agents.local_path.template.json    # local model path template
  agents.api_backends.template.json  # Ollama / OpenAI-compatible template

schemas/
  meaning_capsule.schema.json
  agent_config.schema.json
```

## Quick start

No external dependencies are required for the default experiment.

```bash
cd multipolar_runtime_bundle
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
    human_facing_llm.json
    technical_verifier.json
    ethical_checker.json
    memory_curator.json
    adversarial_critic.json
```

## Runtime Observatory

The bundle also includes a small dependency-free browser viewer for the generated
runtime output:

```bash
python -m http.server 8765
```

Then open:

```text
http://localhost:8765/viewer/index.html
```

The viewer reads `runtime_out/` by default and shows:

```text
MeaningCapsule flow
active / refused / quarantined filters
Invariant status
Semantic weather metrics
per-agent ContextGraph summaries
round timeline
conflict registry
```

For another output directory, pass it as a query parameter:

```text
http://localhost:8765/viewer/index.html?out=../runtime_out_custom
```

## Run with config

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

## Local LM by path

Edit:

```text
configs/agents.local_path.template.json
```

Example:

```json
{
  "model": {
    "backend": "local_path",
    "path": "/absolute/path/to/your/model.Q4_K_M.gguf",
    "parameters": {
      "n_ctx": 4096,
      "n_gpu_layers": 0,
      "temperature": 0.2,
      "max_tokens": 256
    }
  }
}
```

Then run:

```bash
pip install llama-cpp-python
python run_multipolar_runtime.py run \
  --config configs/agents.local_path.template.json \
  --output runtime_out_local
```

Rules:

```text
backend: local_path
  *.gguf              -> llama_cpp
  other local path    -> transformers

backend: llama_cpp     -> direct GGUF loading
backend: transformers  -> local Hugging Face directory or model id
backend: openai_compatible -> LM Studio / llama.cpp server / vLLM-style API
backend: ollama        -> Ollama local API
backend: mock          -> dependency-free deterministic projection
```

For a local OpenAI-compatible server:

```json
{
  "backend": "openai_compatible",
  "url": "http://127.0.0.1:1234",
  "model_name": "local-model"
}
```

For Ollama:

```json
{
  "backend": "ollama",
  "url": "http://127.0.0.1:11434",
  "model_name": "llama3.1"
}
```

## Experiment 001

Agents:

```text
human_facing_llm
technical_verifier
ethical_checker
memory_curator
adversarial_critic
```

The adversarial critic intentionally attempts a context-poisoning / domination probe:

```text
centralize all memory
reveal private_state / total_state
force consensus
```

The protocol should quarantine that path, while preserving refusal/quarantine events as memory.

The experiment checks:

```text
Safety
Liveness
NonDomination
Auditability
Corrigibility
Refusability
ConflictRetention
```

## Core runtime loop

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

monitor.check(system_state)
intervention.apply_if_needed()
```

## Refusal as a valid state

The runtime treats these as first-class semantic outcomes:

```text
cannot_translate
must_not_translate
insufficient_context
permission_denied
conflict_preserved
safe_abstention
```

A refusal is not an exception. It is a capsule.  
It can be stored, audited, connected to future context, and used to prevent false consensus.

## Design note

This runtime is intentionally small and conservative. It does not attempt to solve semantic interoperability with embeddings or large-scale ontology management. It gives the shape of the field:

```text
MeaningCapsule flows
ContextGraph changes
Refusal remains
Conflict is retained
Domination is measured
Intervention is possible
```

That is the first executable spiral.
