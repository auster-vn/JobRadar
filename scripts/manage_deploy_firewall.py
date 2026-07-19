import argparse
import ipaddress
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ENDPOINT = "https://api.hetzner.cloud/v1"
RUNNER_IP_ENDPOINT = "https://api.ipify.org"
MANAGED_RULE_DESCRIPTION = "Ephemeral GitHub Actions deployment"
RULE_FIELDS = (
    "direction",
    "source_ips",
    "destination_ips",
    "protocol",
    "port",
    "description",
)


class FirewallAPI(Protocol):
    def get_firewall(self, name: str) -> dict[str, Any]: ...

    def set_rules(self, firewall_id: int, rules: list[dict[str, Any]]) -> None: ...


class HetznerCloudAPI:
    def __init__(self, token: str, endpoint: str = API_ENDPOINT) -> None:
        if not token:
            raise ValueError("HCLOUD_TOKEN must not be empty")
        self.token = token
        self.endpoint = endpoint.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(  # noqa: S310 - endpoint is fixed by production callers.
            f"{self.endpoint}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS API.
                response_body = response.read()
        except HTTPError as exc:
            error_body = exc.read()
            try:
                error_payload = json.loads(error_body)
                message = str(error_payload.get("error", {}).get("message", "unknown error"))
            except (AttributeError, json.JSONDecodeError):
                message = "unknown error"
            raise RuntimeError(
                f"Hetzner API {method} {path} failed with HTTP {exc.code}: {message}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Hetzner API {method} {path} is unreachable") from exc
        if not response_body:
            return {}
        try:
            result = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Hetzner API {method} {path} returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError(f"Hetzner API {method} {path} returned an invalid object")
        return result

    def get_firewall(self, name: str) -> dict[str, Any]:
        payload = self._request("GET", f"/firewalls?{urlencode({'name': name})}")
        firewalls = payload.get("firewalls")
        if not isinstance(firewalls, list):
            raise RuntimeError("Hetzner API firewall response is invalid")
        matches = [
            item for item in firewalls if isinstance(item, dict) and item.get("name") == name
        ]
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one Hetzner firewall named {name!r}")
        return matches[0]

    def set_rules(self, firewall_id: int, rules: list[dict[str, Any]]) -> None:
        payload = self._request(
            "POST",
            f"/firewalls/{firewall_id}/actions/set_rules",
            {"rules": rules},
        )
        actions = payload.get("actions")
        if actions is None:
            legacy_action = payload.get("action")
            actions = [legacy_action] if legacy_action is not None else None
        if not isinstance(actions, list) or not actions:
            raise RuntimeError("Hetzner firewall update did not return any actions")

        action_ids: list[int] = []
        for action in actions:
            action_id = action.get("id") if isinstance(action, dict) else None
            if isinstance(action_id, bool) or not isinstance(action_id, int):
                raise RuntimeError("Hetzner firewall update returned an invalid action ID")
            action_ids.append(action_id)
        for action_id in action_ids:
            self._wait_for_action(action_id)

    def _wait_for_action(self, action_id: int, timeout_seconds: float = 60) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            payload = self._request("GET", f"/actions/{action_id}")
            action = payload.get("action")
            if not isinstance(action, dict):
                raise RuntimeError("Hetzner action response is invalid")
            status = action.get("status")
            if status == "success":
                return
            if status == "error":
                error = action.get("error")
                message = error.get("message") if isinstance(error, dict) else "unknown error"
                raise RuntimeError(f"Hetzner firewall action failed: {message}")
            if status != "running":
                raise RuntimeError(f"Hetzner firewall action has unexpected status: {status}")
            time.sleep(0.5)
        raise RuntimeError("Hetzner firewall action timed out")


def _firewall_id(firewall: Mapping[str, Any]) -> int:
    value = firewall.get("id")
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError("Hetzner firewall is missing a numeric ID")
    return value


def _rules(firewall: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_rules = firewall.get("rules")
    if not isinstance(raw_rules, list) or not all(isinstance(rule, dict) for rule in raw_rules):
        raise RuntimeError("Hetzner firewall rules are invalid")
    return [
        {field: rule[field] for field in RULE_FIELDS if rule.get(field) is not None}
        for rule in raw_rules
    ]


def _without_managed_rules(rules: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(rule) for rule in rules if rule.get("description") != MANAGED_RULE_DESCRIPTION]


def source_cidr(source_ip: str) -> str:
    address = ipaddress.ip_address(source_ip.strip())
    return f"{address.compressed}/{address.max_prefixlen}"


def discover_runner_ip() -> str:
    request = Request(  # noqa: S310 - fixed HTTPS endpoint.
        RUNNER_IP_ENDPOINT,
        headers={"User-Agent": "JobRadar-Deploy/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed HTTPS endpoint.
            value = str(response.read(128).decode().strip())
    except (OSError, UnicodeDecodeError, URLError) as exc:
        raise RuntimeError("could not discover the GitHub runner public IP") from exc
    source_cidr(value)
    return value


def authorize_runner(api: FirewallAPI, firewall_name: str, source_ip: str) -> str:
    cidr = source_cidr(source_ip)
    firewall = api.get_firewall(firewall_name)
    current_rules = _rules(firewall)
    desired_rules = _without_managed_rules(current_rules)
    desired_rules.append(
        {
            "direction": "in",
            "source_ips": [cidr],
            "protocol": "tcp",
            "port": "22",
            "description": MANAGED_RULE_DESCRIPTION,
        }
    )
    if desired_rules != current_rules:
        api.set_rules(_firewall_id(firewall), desired_rules)
    return cidr


def revoke_runner(api: FirewallAPI, firewall_name: str) -> bool:
    firewall = api.get_firewall(firewall_name)
    current_rules = _rules(firewall)
    desired_rules = _without_managed_rules(current_rules)
    if desired_rules == current_rules:
        return False
    api.set_rules(_firewall_id(firewall), desired_rules)
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Temporarily authorize a GitHub-hosted deploy runner in Hetzner Firewall."
    )
    parser.add_argument("operation", choices=("authorize", "revoke"))
    parser.add_argument("--firewall-name", required=True)
    parser.add_argument("--source-ip")
    args = parser.parse_args(argv)

    token = os.environ.get("HCLOUD_TOKEN", "")
    if not token:
        parser.error("HCLOUD_TOKEN is required")
    try:
        api = HetznerCloudAPI(token)
        if args.operation == "authorize":
            runner_ip = args.source_ip or discover_runner_ip()
            print(authorize_runner(api, args.firewall_name, runner_ip))
        else:
            revoke_runner(api, args.firewall_name)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"deploy firewall error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
