"""Pure session-state merge logic — no I/O, table-driven unit tests live here."""

from datetime import date, timedelta

from resham.schemas.session import IntentExtractionResult, SessionState


def _dedup(items: list[str]) -> list[str]:
    """Deduplicate case-insensitively while preserving first-seen order/casing."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _deadline_from_urgency(urgency_days: int) -> date:
    return date.today() + timedelta(days=urgency_days)


# Some style descriptors are mutually exclusive restatements, not additive
# preferences — a shopper who says "western" after "eastern" changed their
# mind, they don't now want both. Left as plain accumulation, a later
# "eastern" only ever appended alongside a stale "western" already in the
# list, and requested_tradition()/requested_formality() then had to guess
# which one "wins" — real observed bug: that guess preferred "eastern"
# unconditionally, so a later, explicit "western" request was silently
# discarded in favor of a stale first mention.
_EXCLUSIVE_STYLE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"eastern", "western", "fusion"}),
    frozenset({"formal", "casual", "semi-formal", "party", "bridal"}),
)


def _drop_superseded_style_groups(prior: list[str], incoming: list[str]) -> list[str]:
    incoming_lower = {item.lower().strip() for item in incoming}
    result = prior
    for group in _EXCLUSIVE_STYLE_GROUPS:
        if group & incoming_lower:
            result = [item for item in result if item.lower().strip() not in group]
    return result


def merge_session_state(
    current: SessionState, diff: IntentExtractionResult
) -> SessionState:
    """Merge an LLM/fast-path diff into the current session state.

    Rules (TDD §6):
    - occasion/color_preference/size/budget_min/budget_max: explicit new
      values overwrite.
    - style_descriptors/excluded: accumulate rather than overwrite *within
      the same topic* — a genuine topic change (occasion changes) resets
      style_descriptors along with deadline_date, since style words
      describing the old occasion ("traditional" for a wedding) don't
      carry over to a genuinely new one ("casual" for a daily-wear ask).
      Real bug this fixes: style_descriptors accumulated forever with no
      reset at all, so the displayed "Style" chip — which shows the
      *oldest* accumulated word — stayed stuck on whatever was said
      first, no matter how much the shopper's intent moved on.
    - brands is untouched here — only mutated by the fast-path "different
      brand" rule, not by LLM diffs, in this phase.
    """
    cleared = set(diff.clear_fields)
    topic_changed = diff.occasion is not None and diff.occasion != current.occasion

    if diff.urgency_days is not None:
        deadline_date = _deadline_from_urgency(diff.urgency_days)
    elif topic_changed:
        deadline_date = None
    else:
        deadline_date = current.deadline_date

    prior_style_descriptors = (
        [] if topic_changed or "style" in cleared else current.style_descriptors
    )
    removed_styles = {style.lower().strip() for style in diff.remove_styles}
    prior_style_descriptors = [
        style for style in prior_style_descriptors
        if style.lower().strip() not in removed_styles
    ]
    prior_style_descriptors = _drop_superseded_style_groups(
        prior_style_descriptors, diff.style_descriptors
    )

    field_aliases = {
        "color": "color_preference",
        "budget": "budget_max",
        "style": "style_descriptors",
        "age": "child_age_months",
    }
    cleared_constraint_fields = {
        field_aliases.get(field, field) for field in cleared
    }
    if "budget" in cleared:
        cleared_constraint_fields.add("budget_min")
    prior_hard = [
        field for field in current.hard_constraints
        if field not in cleared_constraint_fields
    ]
    prior_soft = [
        field for field in current.soft_preferences
        if field not in cleared_constraint_fields
    ]
    hard_constraints = _dedup(prior_hard + list(diff.hard_constraints))
    hard_keys = {field.lower() for field in hard_constraints}
    soft_preferences = [
        field for field in _dedup(prior_soft + list(diff.soft_preferences))
        if field.lower() not in hard_keys
    ]

    return SessionState(
        occasion=(
            None if "occasion" in cleared
            else diff.occasion if diff.occasion is not None else current.occasion
        ),
        category=(
            None if "category" in cleared
            else diff.category if diff.category is not None else current.category
        ),
        color_preference=(
            None if "color" in cleared else diff.color_preference
            if diff.color_preference is not None
            else current.color_preference
        ),
        # Explicit value > cleared > carry-forward: a fast-path match that
        # both states a new budget_max and clears "budget" (see
        # fast_path_classifier._match_cheaper) must have the new value win,
        # not be wiped out by its own clear_fields entry.
        budget_min=(
            diff.budget_min if diff.budget_min is not None
            else None if "budget" in cleared
            else current.budget_min
        ),
        budget_max=(
            diff.budget_max if diff.budget_max is not None
            else None if "budget" in cleared
            else current.budget_max
        ),
        style_descriptors=_dedup(prior_style_descriptors + diff.style_descriptors),
        size=None if "size" in cleared else current.size if diff.size is None else diff.size,
        deadline_date=deadline_date,
        excluded=_dedup(current.excluded + diff.excluded),
        brands=current.brands,
        department=diff.department if diff.department is not None else current.department,
        wants_kids=diff.wants_kids if diff.wants_kids is not None else current.wants_kids,
        child_age_months=(
            None if "age" in cleared else diff.child_age_months
            if diff.child_age_months is not None
            else current.child_age_months
        ),
        semantic_query=diff.semantic_query.strip() or current.semantic_query,
        hard_constraints=hard_constraints,
        soft_preferences=soft_preferences,
    )
