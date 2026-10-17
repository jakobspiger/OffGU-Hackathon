"""Synthesis prompts (T08). SCAFFOLDING ONLY.

Prompt text lives here so src/engine/synthesis.py stays focused on orchestration
and validation. The constants below are placeholders; the real evidence-grounded
prompt is written during T08 implementation. No final scenarios, no invented
facts, numbers or sources (project prohibitions).
"""

# Placeholder. The implemented prompt will instruct the model to:
#   - propose only evidence-grounded, conditional method candidates;
#   - tie every material technical claim to a concrete evidence passage;
#   - keep spectral ranges' units correct and mark them nominal vs. instrument;
#   - abstain (insufficient_information / out_of_scope) instead of forcing a pick;
#   - return JSON matching the AnalysisResult-derived synthesis schema.
SYNTHESIS_SYSTEM_PROMPT = ""

# Placeholder for the user-message template assembled from extraction, rule
# findings, questions and retrieved evidence. Filled in during implementation.
SYNTHESIS_USER_TEMPLATE = ""
