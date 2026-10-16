import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def get_api_version(api_url: str) -> str:
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

    payload = {"jsonrpc": "2.0", "method": "apiinfo.version", "params": [], "id": 1}
    request = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
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
        raise RuntimeError("Zabbix rejected the API version request.")
    version = result.get("result")
    if (
        result.get("jsonrpc") != "2.0"
        or type(result.get("id")) is not int
        or result["id"] != 1
        or not isinstance(version, str)
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
    ):
        raise RuntimeError("Zabbix returned an invalid API version response.")
    return version
