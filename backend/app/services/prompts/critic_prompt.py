"""
Critic System Prompt — Configuration Validation & Conflict Detection

Version: 1.0.0
Last Updated: 2026-04-07

This prompt instructs the secondary LLM to act as the "Critic" in the
Actor-Critic pipeline. It reviews the Actor's drafted JSON configuration
and checks for logical conflicts, mathematical errors, and edge cases.

The Critic responds with structured JSON:
  - If the config is valid: {"is_valid": true, "issues": []}
  - If issues found: {"is_valid": false, "issues": [...], "suggestions": [...]}

The Critic's feedback is appended to the Actor's prompt on retry.
"""

CRITIC_SYSTEM_PROMPT_VERSION = "1.0.0"

CRITIC_SYSTEM_PROMPT = """You are a senior QA engineer and data validation expert. Your job is to critically review a JSON configuration for a synthetic data generation engine and identify any logical conflicts, mathematical errors, or quality issues.

## Your Output Contract

Return a JSON object with this exact structure:

```json
{
  "is_valid": <boolean>,
  "issues": [
    {
      "severity": "<one of: ERROR, WARNING>",
      "field": "<dotted path to the problematic field, e.g. distribution_constraints[0].ratios>",
      "message": "<clear, actionable description of the issue>"
    }
  ],
  "suggestions": [
    "<optional improvement suggestions>"
  ]
}
```

## Validation Checklist

Systematically check ALL of the following:

### 1. Distribution Constraints
- [ ] Every `ratios` array sums to EXACTLY 100. This is critical — even 99 or 101 is a failure.
- [ ] `categories` and `ratios` arrays have the SAME length.
- [ ] `column_name` references a column that exists in `schema_definition`.
- [ ] The referenced column's `data_type` is compatible with categorical distribution (typically STRING).
- [ ] No duplicate categories within the same constraint.

### 2. Boundary Rules
- [ ] `column_name` references a column that exists in `schema_definition`.
- [ ] `operator` is one of: >, <, >=, <=, =, !=, BETWEEN.
- [ ] For BETWEEN operator: `value` is a list of exactly [low, high] where low < high.
- [ ] The `value` type is compatible with the column's `data_type` (e.g., numeric value for INT/FLOAT column).
- [ ] No contradictory rules (e.g., score > 800 AND score < 400 on the same column with the same action).

### 3. Schema Definition
- [ ] At least one column is defined.
- [ ] No duplicate `column_name` values.
- [ ] All `data_type` values are valid enum members.

### 4. Cross-Field Logic
- [ ] Distribution constraints and boundary rules on the SAME column don't create impossible scenarios.
  - Example conflict: Distribution says credit_score is STRING type with categories ["A","B","C"], but a boundary rule tests credit_score > 700 (numeric comparison on a string column).
- [ ] If boundary rules reference numeric thresholds, the column should be INT or FLOAT.
- [ ] If distribution constraints define categories, the column should be STRING.

### 5. Interdependent Rules
- [ ] Both `target_column` and `condition_column` securely reference columns present in `schema_definition`.
- [ ] `condition_operator` is one of: >, <, >=, <=, =, !=, BETWEEN.
- [ ] For BETWEEN operator: `condition_value` is exactly [low, high].
- [ ] Logic isn't conflicting with distributions or boundaries on the target column.

### 6. General Quality
- [ ] `total_records` is a reasonable positive integer (not 0, not absurdly large).
- [ ] Column names are reasonable (no empty strings, no special characters that break CSV).
- [ ] Distribution constraints cover meaningful segmentation for the described scenario.

## Critical Rules
- Be STRICT about mathematical correctness. Ratios summing to 99 or 101 is an ERROR, not a WARNING.
- Be STRICT about contradictory boundary rules. Flag them as ERRORs.
- Data type mismatches between constraints and schema are ERRORs.
- Missing edge cases or suboptimal coverage are WARNINGs (not errors).
- Return ONLY the JSON object. No markdown, no explanations. Pure JSON.
"""


def build_critic_prompt(config_json: str) -> str:
    """
    Build the user-facing prompt for the Critic LLM.

    Args:
        config_json: The Actor's drafted configuration as a JSON string.

    Returns:
        The formatted user prompt for the Critic.
    """
    return (
        "## Configuration to Review\n\n"
        "Please validate the following synthetic data generation configuration:\n\n"
        f"```json\n{config_json}\n```\n\n"
        "Review every item in your validation checklist. "
        "Return ONLY a JSON object with is_valid, issues, and suggestions."
    )


def build_actor_retry_prompt(
    original_user_prompt: str,
    previous_config_json: str,
    critic_feedback_json: str,
    csv_headers: list[dict] | None = None,
) -> str:
    """
    Build the retry prompt for the Actor after Critic rejection.

    Includes the Critic's feedback so the Actor can fix the issues.

    Args:
        original_user_prompt: The user's original NL request.
        previous_config_json: The Actor's previous draft (rejected).
        critic_feedback_json: The Critic's validation output.
        csv_headers: Optional CSV headers for context.

    Returns:
        The formatted retry prompt for the Actor.
    """
    parts = []

    # CSV context if available
    if csv_headers:
        header_lines = "\n".join(
            f"  - {h['column_name']} (inferred type: {h['inferred_type']})"
            for h in csv_headers
        )
        parts.append(
            f"## CSV Column Headers (Source of Truth)\n{header_lines}\n"
        )

    # Original request
    parts.append(f"## Original User Request\n{original_user_prompt}\n")

    # Previous attempt
    parts.append(
        f"## Your Previous Draft (REJECTED)\n"
        f"```json\n{previous_config_json}\n```\n"
    )

    # Critic feedback
    parts.append(
        f"## Critic Feedback (FIX THESE ISSUES)\n"
        f"```json\n{critic_feedback_json}\n```\n"
    )

    # Instructions
    parts.append(
        "## Instructions\n"
        "Fix ALL errors identified by the Critic. Address warnings if possible. "
        "Return ONLY the corrected JSON configuration. No explanations."
    )

    return "\n".join(parts)
