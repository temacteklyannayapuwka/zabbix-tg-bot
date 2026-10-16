from datetime import datetime


SEVERITIES = (
    "Not classified", "Information", "Warning", "Average", "High", "Disaster"
)


def format_notification(event: dict) -> str:
    if event.get("status") != "problem":
        raise ValueError("Event status must be 'problem'.")
    for field in ("event_id", "host", "name", "occurred_at"):
        if not isinstance(event.get(field), str) or not event[field].strip():
            raise ValueError(f"Event field '{field}' must be a non-empty string.")
    severity = event.get("severity")
    if type(severity) is not int or not 0 <= severity < len(SEVERITIES):
        raise ValueError("Event severity must be an integer from 0 to 5.")
    try:
        timestamp = datetime.fromisoformat(event["occurred_at"])
    except ValueError:
        raise ValueError("Event occurred_at must be an ISO 8601 timestamp.") from None
    if timestamp.utcoffset() is None:
        raise ValueError("Event occurred_at must include a timezone.")
    message = (
        f"🔴 Problem\nHost: {event['host']}\nProblem: {event['name']}\n"
        f"Severity: {SEVERITIES[severity]}\nOccurred: {event['occurred_at']}\n"
        f"Event: {event['event_id']}"
    )
    if len(message) > 4096:
        raise ValueError("Notification exceeds 4096 characters.")
    return message
