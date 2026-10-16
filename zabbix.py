import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _api_request(api_url: str, method: str, params, token: str | None = None):
    try:
        url = urlsplit(api_url)
        valid = (
            url.scheme in ("http", "https")
            and url.hostname
            and url.path.endswith("/api_jsonrpc.php")
            and not url.username
            and not url.password
            and not url.query
            and not url.fragment
        )
        url.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Set ZABBIX_API_URL to an HTTP(S) URL ending in /api_jsonrpc.php.")

    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    open_request = urlopen if token is None else build_opener(_NoRedirect()).open
    try:
        with open_request(request, timeout=15) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Zabbix returned HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError("Could not connect to Zabbix. Check the URL and network.") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("Zabbix returned an invalid JSON response.") from None

    if not isinstance(result, dict):
        raise RuntimeError("Zabbix returned an invalid API response.")
    if "error" in result:
        raise RuntimeError("Zabbix rejected the API request. Check the token and API permissions.")
    if (
        result.get("jsonrpc") != "2.0"
        or type(result.get("id")) is not int
        or result["id"] != 1
        or "result" not in result
    ):
        raise RuntimeError("Zabbix returned an invalid API response.")
    return result["result"]


def get_api_version(api_url: str) -> str:
    version = _api_request(api_url, "apiinfo.version", [])
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise RuntimeError("Zabbix returned an invalid API version response.")
    return version


def get_problems(api_url: str, token: str) -> list[dict]:
    if not token or not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
        raise ValueError("Set ZABBIX_API_TOKEN to a valid API token.")
    problems = _api_request(api_url, "problem.get", {
        "output": ["eventid", "objectid", "name", "severity", "clock"],
        "source": 0,
        "object": 0,
        "recent": False,
        "sortfield": ["eventid"],
        "sortorder": "DESC",
        "limit": 100,
    }, token)
    if not isinstance(problems, list):
        raise RuntimeError("Zabbix returned an invalid problem list.")
    for problem in problems:
        if not isinstance(problem, dict):
            raise RuntimeError("Zabbix returned an invalid problem.")
        for field in ("eventid", "objectid", "clock"):
            if not isinstance(problem.get(field), str) or not re.fullmatch(r"[0-9]+", problem[field]):
                raise RuntimeError("Zabbix returned an invalid problem.")
        if not isinstance(problem.get("name"), str) or problem.get("severity") not in ("0", "1", "2", "3", "4", "5"):
            raise RuntimeError("Zabbix returned an invalid problem.")
    if not problems:
        return []
    trigger_ids = list(dict.fromkeys(problem["objectid"] for problem in problems))
    triggers = _api_request(api_url, "trigger.get", {
        "triggerids": trigger_ids,
        "output": ["triggerid"],
        "selectHosts": ["hostid", "host", "name"],
    }, token)
    if not isinstance(triggers, list):
        raise RuntimeError("Zabbix returned an invalid trigger list.")
    hosts_by_trigger = {}
    for trigger in triggers:
        if (
            not isinstance(trigger, dict)
            or not isinstance(trigger.get("triggerid"), str)
            or trigger["triggerid"] not in trigger_ids
            or trigger["triggerid"] in hosts_by_trigger
            or not isinstance(trigger.get("hosts"), list)
        ):
            raise RuntimeError("Zabbix returned an invalid trigger.")
        hosts = []
        for host in trigger["hosts"]:
            if (
                not isinstance(host, dict)
                or not isinstance(host.get("hostid"), str)
                or not re.fullmatch(r"[0-9]+", host["hostid"])
                or not isinstance(host.get("host"), str)
                or not host["host"].strip()
                or not isinstance(host.get("name"), str)
            ):
                raise RuntimeError("Zabbix returned an invalid host.")
            hosts.append({field: host[field] for field in ("hostid", "host", "name")})
        hosts_by_trigger[trigger["triggerid"]] = hosts
    return [
        {**problem, "hosts": hosts_by_trigger.get(problem["objectid"], [])}
        for problem in problems
    ]
