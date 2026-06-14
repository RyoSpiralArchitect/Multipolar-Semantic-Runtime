# Scenario Zoo

Scenario Zoo entries package a small cast, a query sequence, and runtime thresholds
into one runnable experiment.

```bash
python run_multipolar_runtime.py list-scenarios
python run_multipolar_runtime.py run --scenario civic_deliberation --output runtime_out_civic
python run_multipolar_runtime.py run-scenario incident_review --output runtime_out_incident
```

Each scenario is ordinary JSON. Agents may include `public_projection` to give the
dependency-free mock backend scenario-specific text, claims, assumptions, and
risk metadata without exposing `private_state`.

Scenarios may also include `story` metadata:

```json
{
  "story": {
    "premise": "Why this multipolar situation exists.",
    "stakes": "What gets lost if the runtime collapses difference.",
    "beats": [
      {
        "round": 1,
        "title": "First pressure",
        "scene": "What the agents are negotiating.",
        "pressure": "What tempts false consensus."
      }
    ]
  }
}
```

The dependency-free viewer renders these beats as a Story Arc and lets readers
branch, roll back, and tune local protocol thresholds without mutating the
exported runtime JSON files. Saved branches can be exported as compact URL
recipes for sharing the playable branch, or as full JSON snapshots for audit and
offline inspection.
