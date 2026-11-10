# SIGNALDESK 0.2.1 — Qwen3 inference stability update

## Changes

- Reduced default Ollama context window from 8192 to 4096 tokens for more conservative VRAM use.
- Reduced default classifier batch size from 15 records to 5.
- Set Ollama prompt-evaluation batch size to 128 tokens to reduce peak allocation pressure.
- Capped generated output at 512 tokens and set a 5-minute model keep-alive.
- Added a one-time inference retry with half the context window and half the prompt-evaluation batch after CUDA/KV-cache allocation errors. This targets the startup error observed on the RTX 4050. Added adaptive batch splitting for other prompt-batch allocation failures. Failed requests are retried before keyword fallback is applied.
- Added retry handling for incomplete model responses: omitted/invalid records are retried in smaller batches.
- Kept immediate fallback for connection failures and other errors that smaller prompts are unlikely to fix.
- Added sanitized warnings that distinguish recovered GPU-memory pressure from records that ultimately required keyword fallback.
- Added `/api/health` inference settings so the active batch/context limits can be checked without exposing secrets.
- Added `scripts/apply_vram_safe_defaults.py`, which updates only inference-related `.env` keys while preserving API tokens, public URL settings, and unrelated environment values.

## Why these changes

The user's 200-record run reported 110 Qwen3 classifications and 90 keyword fallbacks. The backend warning described CUDA/KV-cache allocation failures in six 15-record batches. That is evidence of GPU memory pressure; the earlier inference request used an 8192-token context and a 15-record batch. These changes lower the context and batch footprint and retry only failed portions of a batch.

## Expected behaviour

The update aims to increase Qwen3 coverage while preserving a reliable fallback. It does not guarantee 100% model classification: the RTX 4050's available VRAM depends on display use, other GPU processes, Ollama/model allocation, and feedback length.

## Verification

- Automated tests validate GPU OOM batch splitting, single-record fallback, configured Ollama request limits, and health diagnostics.
- Offline smoke test remains a fallback-only pipeline check; it does not measure live Qwen3 performance.
- Live Qwen3 throughput and classification coverage must be measured on the user's laptop.
