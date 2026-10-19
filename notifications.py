from datetime import datetime, timezone


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


def _zabbix_problem_event(problem: dict) -> dict:
    if not isinstance(problem, dict):
        raise ValueError("Zabbix problem must be an object.")
    for field in ("eventid", "clock", "severity"):
        value = problem.get(field)
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
            raise ValueError(f"Zabbix problem {field} must be a numeric string.")
    try:
        occurred_at = datetime.fromtimestamp(int(problem["clock"]), timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise ValueError("Zabbix problem clock is outside the supported date range.") from None
    hosts = problem.get("hosts")
    if not isinstance(hosts, list):
        raise ValueError("Zabbix problem hosts must be an array.")
    names = []
    for host in hosts:
        if not isinstance(host, dict):
            raise ValueError("Zabbix problem host must be an object.")
        name = host.get("name")
        technical_name = host.get("host")
        if not isinstance(name, str) or not isinstance(technical_name, str) or not technical_name.strip():
            raise ValueError("Zabbix problem host names are invalid.")
        names.append(name.strip() or technical_name.strip())
    return {
        "status": "problem",
        "event_id": problem["eventid"],
        "host": ", ".join(dict.fromkeys(names)) or "Unknown host",
        "name": problem.get("name"),
        "severity": int(problem["severity"]),
        "occurred_at": occurred_at,
    }


def format_zabbix_problem(problem: dict) -> str:
    return format_notification(_zabbix_problem_event(problem))


def format_zabbix_recovery(problem: dict, recovery: dict) -> str:
    event = _zabbix_problem_event(problem)
    if recovery.get("eventid") != problem["eventid"]:
        raise ValueError("Recovery does not match the original problem.")
    clock = recovery.get("r_clock")
    if not isinstance(clock, str) or not clock.isascii() or not clock.isdecimal():
        raise ValueError("Recovery clock must be a numeric string.")
    try:
        recovered_at = datetime.fromtimestamp(int(clock), timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise ValueError("Recovery clock is outside the supported date range.") from None
    return format_notification({**event, "status": "recovery", "recovered_at": recovered_at})
