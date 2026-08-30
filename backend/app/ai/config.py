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
