from datetime import datetime


SEVERITIES = (
    "Not classified", "Information", "Warning", "Average", "High", "Disaster"
)


def format_notification(event: dict) -> str:
    if event.get("status") not in ("problem", "recovery"):
        raise ValueError("Event status must be 'problem' or 'recovery'.")
    for field in ("event_id", "host", "name", "occurred_at"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError(f"Event field '{field}' must be a non-empty string.")
    severity = event.get("severity")
    if type(severity) is not int or not 0 <= severity < len(SEVERITIES):
        raise ValueError("Event severity must be an integer from 0 to 5.")
    timestamps = ["occurred_at"]
    if event["status"] == "recovery":
        timestamps.append("recovered_at")
    parsed = {}
    for field in timestamps:
        if not isinstance(event.get(field), str):
            raise ValueError(f"Event {field} must be an ISO 8601 timestamp.")
        try:
            parsed[field] = datetime.fromisoformat(event[field])
        except ValueError:
            raise ValueError(f"Event {field} must be an ISO 8601 timestamp.") from None
        if parsed[field].utcoffset() is None:
            raise ValueError(f"Event {field} must include a timezone.")
    title = "🔴 Problem"
    if event["status"] == "recovery":
        if parsed["recovered_at"] < parsed["occurred_at"]:
            raise ValueError("Recovery cannot precede the problem.")
        title = "✅ Resolved"
    message = (
        f"{title}\nHost: {event['host']}\nProblem: {event['name']}\n"
        f"Severity: {SEVERITIES[severity]}\nOccurred: {event['occurred_at']}\n"
    )
    if event["status"] == "recovery":
        message += f"Recovered: {event['recovered_at']}\n"
    message += f"Event: {event['event_id']}"
    if len(message) > 4096:
        raise ValueError("Notification exceeds 4096 characters.")
    return message
