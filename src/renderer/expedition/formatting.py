"""Friendly labels and direct projection of validated values; never calculate scores."""

ACTION_LABELS = {
    "READY": "Ready to replay", "MOVE_NORTH": "Move north", "MOVE_EAST": "Move east",
    "MOVE_SOUTH": "Move south", "MOVE_WEST": "Move west", "COLLECT": "Collect artifact",
    "ENGAGE": "Engage enemy", "WAIT": "Wait", "EXIT": "Exit requested", "CALLBACK": "Controller response",
}
REASONS = {
    "PATROL_COLLISION": "Caught by a patrolling enemy", "DEADLINE": "Patrol deadline reached",
    "MAX_TURNS": "Turn limit reached", "FAILED_TURN_LIMIT": "Turn limit reached",
    "TURN_LIMIT": "Turn limit reached", "CONTROLLER_ERROR": "Controller could not continue",
}
SCORING = (
    ("T", "Total turns", "Legal actions in the final recording."),
    ("P", "Encounter cost", "Incurred encounter penalties; not direct point loss."),
    ("A", "Artifact points", "Points from artifacts actually collected."),
    ("C", "Total cost", "Recorded turns plus incurred encounter penalties."),
    ("L", "Baseline completion cost", "Certified minimum no-collection completion cost, including required actions."),
    ("E", "Cost above baseline", "Recorded excess cost above the baseline."),
    ("B", "Base completion points", "Base points in the recording's policy."),
    ("r", "Deduction per excess-cost unit", "The recorded policy deduction rate."),
    ("Q", "Zero-score cutoff", "Excess-cost threshold; not a logical deadline."),
    ("H", "Turn limit", "Hard logical-turn safety limit."),
    ("D", "Patrol deadline", "A separately recorded logical deadline, when applicable."),
    ("score", "Final score", "Validated final score; not a course grade."),
)


def friendly_action(frame):
    if frame.action == "EXIT" and frame.completed: return "Exit accepted"
    return ACTION_LABELS.get(frame.action, "Recorded action")


def current_status(frame, recording):
    if frame.completed: return "Completed — exit accepted"
    if frame.status == "RUNNING":
        return "At exit — waiting for an exit action" if frame.position == recording.exit else "In progress"
    reason = REASONS.get(frame.reason) or REASONS.get(frame.status)
    if reason: return "Run ended — " + reason[0].lower() + reason[1:]
    if frame.accepted is False: return "Run ended — action rejected"
    return "Run ended — details available"


def metric(recording, key):
    values = dict(recording.final_metrics)
    if key == "D" and (values.get(key) == "none" or (key not in values and recording.source_format == "aligned-stage0")):
        return "Not applicable"
    return values.get(key, "Not available")


def compact_value(value, limit=9):
    """A size label is explicitly not the full number; details retain every digit."""
    text = str(value)
    digits = text.lstrip("-")
    if len(text) > limit and digits.isdecimal(): return f"{len(digits):,} digits"
    return text


def current_cards(frame):
    return (("Turn", str(frame.turn)), ("Artifacts remaining", str(len(frame.artifacts))),
            ("Enemies present", str(len(frame.enemies))), ("Tiles visited", str(len(frame.visited))))


def final_cards(recording):
    return (("Total cost", metric(recording, "C")), ("Artifact points", metric(recording, "A")))


def scoring_text(recording):
    lines = ["Final run result — entire recording", "Values are the validated final result, including while viewing earlier frames.", ""]
    for key, label, meaning in SCORING:
        if key == "L" and recording.source_format == "ultra-workbench-public-run":
            meaning = "Public analytic minimum: K-1 moves plus explicit EXIT on the admitted straight path. DEVELOPMENT practice; no course certification."
        elif key == "L" and recording.source_format == "ultra-public-project-run":
            meaning = "Exact public no-collection minimum under this world's actions, penalties and timing; checked from saved proof data. DEVELOPMENT practice; no course grade."
        lines.extend((f"{label}: {metric(recording, key)}", meaning, ""))
    return "\n".join(lines)


def event_groups(recording, index):
    return tuple((f"Frame {frame.index + 1} · Turn {frame.turn} — {friendly_action(frame)}",
                  frame.event_lines) for frame in recording.frames[:index + 1])


def technical_text(recording, frame):
    lines = [f"Record format: {recording.source_format}, version {recording.source_version}",
        f"Selected frame index: {frame.index}", f"Logical turn: {frame.turn}",
        f"Action code: {frame.action}", f"Accepted: {frame.accepted}",
        f"Status code: {frame.status}", f"Reason code: {frame.reason or '(none)'}",
        f"Position (zero-based row, column): {frame.position}",
        "Recorded event order: " + (" > ".join(frame.event_order) or "Not supplied"),
        f"Recorded patrol clock: {frame.patrol_turn if frame.patrol_turn is not None else 'Not applicable'}", ""]
    for a in frame.artifacts: lines.append(f"Artifact ID {a.entity_id}: value {a.value}, position {a.position}")
    for e in frame.enemies:
        lines.append(f"Enemy ID {e.entity_id}: declared encounter penalty {e.value}, position {e.position}")
        if e.patrol: lines.append(f"  Patrol phase index: {e.phase} (schedule position, not elapsed turns)")
    lines.extend(("", "An enemy's declared penalty is potential cost. Final encounter cost records only incurred penalties.",
                  "Full current values: " + "; ".join(f"{label}: {value}" for label, value in current_cards(frame))))
    return "\n".join(lines)
