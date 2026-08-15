from typing import Any

import pytest

from scripts.manage_deploy_firewall import (
    MANAGED_RULE_DESCRIPTION,
    HetznerCloudAPI,
    authorize_runner,
    revoke_runner,
    source_cidr,
)


class EmptyResponse:
    def __enter__(self) -> "EmptyResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b""


class FakeFirewallAPI:
    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self.firewall = {"id": 42, "name": "production-firewall", "rules": rules}
        self.updates: list[tuple[int, list[dict[str, Any]]]] = []

    def get_firewall(self, name: str) -> dict[str, Any]:
        assert name == self.firewall["name"]
        return self.firewall

    def set_rules(self, firewall_id: int, rules: list[dict[str, Any]]) -> None:
        self.updates.append((firewall_id, rules))
        self.firewall["rules"] = rules


BASE_RULE = {
    "direction": "in",
    "source_ips": ["198.51.100.10/32"],
    "protocol": "tcp",
    "port": "22",
    "description": "Restricted administrative SSH",
}


def test_cloud_api_accepts_successful_no_content_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.manage_deploy_firewall.urlopen",
        lambda *_args, **_kwargs: EmptyResponse(),
    )

    api = HetznerCloudAPI("test-token")

    assert api._request("DELETE", "/firewalls/42") == {}


@pytest.mark.parametrize(
    ("response", "expected_action_ids"),
    [
        ({"actions": [{"id": 101}, {"id": 102}]}, [101, 102]),
        ({"action": {"id": 103}}, [103]),
    ],
)
def test_cloud_api_waits_for_every_firewall_action(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
    expected_action_ids: list[int],
) -> None:
    api = HetznerCloudAPI("test-token")
    waited_for: list[int] = []
    monkeypatch.setattr(api, "_request", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(api, "_wait_for_action", waited_for.append)

    api.set_rules(42, [BASE_RULE])

    assert waited_for == expected_action_ids


@pytest.mark.parametrize(
    "response",
    [{}, {"actions": []}, {"actions": [{"id": True}]}, {"actions": [{"id": "101"}]}],
)
def test_cloud_api_rejects_missing_or_invalid_firewall_actions(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> None:
    api = HetznerCloudAPI("test-token")
    monkeypatch.setattr(api, "_request", lambda *_args, **_kwargs: response)

    with pytest.raises(RuntimeError, match="actions|action ID"):
        api.set_rules(42, [BASE_RULE])


def test_authorize_runner_replaces_stale_managed_rule_and_preserves_base_rules() -> None:
    stale = {
        "direction": "in",
        "source_ips": ["192.0.2.8/32"],
        "protocol": "tcp",
        "port": "22",
        "description": MANAGED_RULE_DESCRIPTION,
    }
    api = FakeFirewallAPI([BASE_RULE, stale])

    cidr = authorize_runner(api, "production-firewall", "203.0.113.25")

    assert cidr == "203.0.113.25/32"
    assert api.updates == [
        (
            42,
            [
                BASE_RULE,
                {
                    "direction": "in",
                    "source_ips": ["203.0.113.25/32"],
                    "protocol": "tcp",
                    "port": "22",
                    "description": MANAGED_RULE_DESCRIPTION,
                },
            ],
        )
    ]


def test_revoke_runner_removes_only_managed_rules() -> None:
    managed = {
        "direction": "in",
        "source_ips": ["203.0.113.25/32"],
        "protocol": "tcp",
        "port": "22",
        "description": MANAGED_RULE_DESCRIPTION,
    }
    api = FakeFirewallAPI([BASE_RULE, managed])

    assert revoke_runner(api, "production-firewall")
    assert api.updates == [(42, [BASE_RULE])]
    assert not revoke_runner(api, "production-firewall")
    assert len(api.updates) == 1


def test_source_cidr_accepts_ipv4_and_ipv6_but_rejects_invalid_values() -> None:
    assert source_cidr("203.0.113.25") == "203.0.113.25/32"
    assert source_cidr("2001:db8::25") == "2001:db8::25/128"
    with pytest.raises(ValueError, match="does not appear to be an IPv4 or IPv6 address"):
        source_cidr("not-an-ip")
