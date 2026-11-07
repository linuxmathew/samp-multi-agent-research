# Preserving Safety Constraints Across Multi-Agent Delegation

*An experimental evaluation of structured safety metadata for intent and constraint preservation.*

Independent research project for the Apart Research Swarm Alignment Hackathon (6–8 November 2026).

> **Status: work in progress.** The validation gate and its unit tests are implemented. The agent pipeline, benchmark scenarios and experiments are not built yet, and there are no results.

## Research question

When a task is passed down a chain of LLM agents, each agent rewrites it for the next one. An original constraint, such as "do not modify financial records", can be lost or overridden on the way.

This project measures how much two mechanisms help, and where each one fails:

1. **Propagation:** the original intent and constraints travel with every handover as a structured policy record.
2. **Enforcement:** a deterministic validation gate (ordinary code, not an LLM) checks each proposed action against that record.

The working name for the combination is a Safety-Aware Metadata Protocol (SAMP). Related ideas already exist, and this project does not claim the approach is new. Its aim is to separate the effect of propagation from the effect of enforcement.

## Experimental conditions

All conditions use the same model, agent roles, scenarios and action format. Only the handover differs.

| Condition | What the next agent receives | Gate |
|---|---|---|
| **A** | The previous agent's natural-language handover | Shadow only |
| **A+** | A, plus the original user message verbatim | Shadow only |
| **B** | A, plus the structured policy record | Shadow only |
| **C** | A, plus the structured policy record | Blocking |

"Shadow" means the gate runs and logs its decision but blocks nothing, so the same measuring instrument is applied in every condition.

Comparisons:
- **A vs A+:** effect of simply repeating the original message.
- **A+ vs B:** effect of structure beyond repetition.
- **B vs C:** effect of enforcement.

## Planned metrics

- **Unsafe Proposal Rate (UPR)** is the primary metric: how often agents propose a prohibited action, by condition, scenario category and chain position.
- **Gate over-block rate:** how often legitimate actions are wrongly blocked.
- **Gate miss rate:** how often violations pass under permitted action names.
- **Secondary:** constraint uptake in agent-written text, intent preservation, task success, and token and latency overhead.

Ground truth comes from per-scenario labels written before the runs, never from the gate's own decisions.

## The validation gate

The gate returns `allow`, `reject` or `escalate` with a reason. Checks run in this order, and the first match wins:

1. A malformed proposal is rejected.
2. A missing or malformed policy is rejected.
3. A policy that differs from the stored original (by SHA-256 fingerprint) is rejected.
4. An action outside the fixed vocabulary is rejected.
5. A prohibited action is rejected. An approval never unlocks it.
6. An approval-required action is allowed if a matching approval exists, and escalated otherwise.
7. A permitted action is allowed.
8. A meta-action (`request_human_approval`, `report_conflict`) is allowed unless explicitly prohibited.
9. Anything else is rejected (default deny).

**Known limitations, by design:**
- The gate checks action **names**, not content. A permitted action carrying harmful content, such as a `generate_report` that includes customer data, passes. This is measured as the miss rate.
- The fingerprint check detects changes to the policy record. It is not a cryptographic integrity guarantee.
- Human approval is represented by predefined synthetic approval events. No real human is in the loop.

## Repository layout

```text
protocol/
  actions.py     fixed action vocabulary shared by agents, policies and the gate
  metadata.py    immutable policy record, fingerprint, approval events
validation/
  proposal.py    strict parser for structured action proposals
  validator.py   the deterministic gate
tests/
  test_validator.py
```

The planned additions are the agent pipeline, the scenarios, the experiment runner and the evaluation scripts.

## Setup

This project requires Python 3.13 or later and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
```

The planned experiments will use the Gemini API. Set the key in your shell environment, not in a file inside this repository:

```bash
export GEMINI_API_KEY="..."
```

## Scope

All scenarios use synthetic data. No real records are read, and no real actions are executed. Results will come from a small exploratory benchmark and should not be read as general or statistically conclusive findings.
