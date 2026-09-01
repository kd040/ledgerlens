"""AI Investigator configuration -- isolated here so the model AND the
provider can be swapped by editing one constant or an env var, with no
change to investigator.py or the provider implementations.

AI_PROVIDER selects which backend/app/ai/providers/*.py implementation
run_ai_investigation uses. "gemini" is the default because this project
currently runs its live/free-tier verification against Gemini; set
AI_PROVIDER=anthropic to use the still-fully-supported Anthropic path
instead (requires ANTHROPIC_API_KEY).
"""

import os

AI_PROVIDER = (os.getenv("AI_PROVIDER") or "gemini").strip().lower()

# --------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------
# No live benchmark has been run for the Anthropic path in this
# environment (no ANTHROPIC_API_KEY configured here) -- this default is
# Anthropic's own current documented recommendation for reasoning/
# agentic-tool-use work of this shape, not a measured result.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
ANTHROPIC_MAX_TOKENS = 4096
ANTHROPIC_REQUEST_TIMEOUT_SECONDS = 60.0

# --------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------
# Chosen from a live check of the models actually available to the
# configured GEMINI_API_KEY (see the Phase 3 report): the plain
# "gemini-flash-latest" alias was returning transient 503s at
# verification time, while "gemini-flash-lite-latest" round-tripped
# real multi-turn function calling successfully. Both are Google's own
# rolling aliases, not a snapshot -- Google keeps them pointed at their
# current recommended model, so this can't quietly go obsolete the way
# a pinned "gemini-2.5-flash"-style name did (confirmed 404 "no longer
# available to new users" for this same key during the same check).
DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
GEMINI_MAX_OUTPUT_TOKENS = 4096
GEMINI_REQUEST_TIMEOUT_MS = 60_000

# --------------------------------------------------------------------
# Shared free-tier / runaway-loop safety -- applied to every provider,
# not just Gemini, so neither backend can spin an unbounded number of
# API calls against one investigation.
# --------------------------------------------------------------------
MAX_TOOL_TURNS = 12  # model round-trips (API calls) per investigation
MAX_TOTAL_TOOL_CALLS = 20  # individual tool invocations across all turns

# --------------------------------------------------------------------
# Groq -- transient-failure fallback for the primary provider
# --------------------------------------------------------------------
# Groq exposes an OpenAI-compatible Chat Completions API, so the provider
# talks to it over plain HTTP with the already-pinned httpx rather than
# pulling in a whole extra SDK for one endpoint.
#
# openai/gpt-oss-120b is a current Groq *production* model (checked
# against console.groq.com/docs/models): 131k context, supports OpenAI
# function calling, and is the migration target Groq itself names for the
# llama-3.x models it deprecated on 2026-06-17 -- so this default does not
# start out pointing at something already on the way out. The 120b is
# preferred over the 20b because this is structured financial reasoning
# over multi-turn tool evidence, not a latency-critical path (it only
# ever runs when Gemini is already failing).
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_MODEL = os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1"
# Sized from measurement, not habit. A deliberately generous real
# AiInvestigationResult -- 6 evidence items, 3 hypotheses, a
# contradiction and long prose in every assessment field -- tokenizes to
# 874 tokens under gpt-oss's o200k_harmony encoding; a minimal valid one
# is 399. 2048 leaves 2.3x headroom over that generous case for the
# model's reasoning tokens, which also bill against this ceiling.
#
# This number is not cosmetic: Groq debits TPM as
# prompt + max_completion_tokens, reserved up front. At 4096 a single
# turn cost 5476 of an 8000 TPM budget, so the SECOND turn of the
# tool-calling loop was rate-limited every time and the fallback could
# never finish an investigation. At 2048 a turn costs ~3428, so two fit
# in one window.
#
# Lowering it further is a truncation risk, not a saving: a cut-off
# submit call is malformed JSON, which fails the whole fallback.
GROQ_MAX_COMPLETION_TOKENS = 2048
GROQ_REQUEST_TIMEOUT_SECONDS = 60.0
# gpt-oss is a reasoning model and its reasoning tokens are billed as
# completion tokens while never appearing in AiInvestigationResult. The
# investigation's thinking is externalised as tool calls and the
# structured hypotheses/root_cause_assessment fields, so paying for long
# hidden chains of thought buys nothing here. "low" is Groq's supported
# value for gpt-oss (alongside "medium"/"high").
GROQ_REASONING_EFFORT = "low"
# Forced function calling, mirroring Gemini's FunctionCallingConfigMode.ANY,
# so both providers are held to "answer with a tool call, never prose".
# Verified against the live Groq API: openai/gpt-oss-120b accepts
# tool_choice="required" (the request reached the model and was not
# rejected as a 400). Kept as a constant rather than inlined so that if a
# future Groq model ever stops supporting it, this is the single line to
# change to "auto".
GROQ_TOOL_CHOICE = "required"

# --------------------------------------------------------------------
# Failover policy (see app/ai/providers/failover.py)
# --------------------------------------------------------------------
# Exactly one retry of the primary before falling back. The worst case is
# therefore 3 provider attempts, and the backoff is deliberately sub-second
# so a failing run still returns well inside Render's request timeout
# rather than turning a 503 into a 502 gateway timeout.
PRIMARY_RETRY_ATTEMPTS = 1
RETRY_BACKOFF_SECONDS = 0.5
RETRY_BACKOFF_JITTER_SECONDS = 0.25

# A 429 from the fallback carries a provider-directed Retry-After. It is
# worth honouring, but ONLY when the provider asks for a genuinely short
# wait -- a free-tier TPM window typically advertises ~21s, which would
# push a request that has already spent time on two Gemini attempts past
# the deployment's timeout and turn a clean 503 into a gateway 502.
#
# So: at most one extra fallback attempt, taken only if the provider's
# own Retry-After fits inside both this cap and the retry budget below.
# Never an unbounded wait, and never a wait we invented ourselves.
FALLBACK_RETRY_AFTER_MAX_SECONDS = 5.0
# Deadline, measured from the start of the provider chain, after which a
# provider-directed Retry-After sleep is no longer worth entering.
#
# Scope note: this bounds the WAIT, not the request. It does not cap how
# long the providers themselves may take -- each carries its own request
# timeout (GEMINI_REQUEST_TIMEOUT_MS, GROQ_REQUEST_TIMEOUT_SECONDS) and
# those still apply on top. The purpose here is narrow and specific: once
# this much time has already gone into a request, sleeping further before
# one more fallback attempt is more likely to hit the deployment's
# timeout than to succeed, so the chain fails fast into the clean 503
# instead.
AI_FALLBACK_RETRY_BUDGET_SECONDS = 60.0
