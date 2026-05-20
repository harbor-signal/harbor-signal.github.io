from __future__ import annotations

from scripts.fetch_ais import aisstream_connection_hosts


def test_uses_default_dns_when_no_connection_hostname_is_configured() -> None:
    assert aisstream_connection_hosts({}, resolver=lambda hostname: ["should-not-resolve"]) == [None]


def test_resolves_configured_connection_hostname_for_verified_tls_override() -> None:
    hosts = aisstream_connection_hosts(
        {"AISSTREAM_CONNECT_HOSTNAME": "aisstream.io"},
        resolver=lambda hostname: ["104.21.18.245", "172.67.183.244"] if hostname == "aisstream.io" else [],
    )

    assert hosts == ["104.21.18.245", "172.67.183.244"]


def test_explicit_connection_hosts_take_precedence() -> None:
    hosts = aisstream_connection_hosts(
        {
            "AISSTREAM_CONNECT_HOSTS": "203.0.113.10, 203.0.113.11",
            "AISSTREAM_CONNECT_HOSTNAME": "aisstream.io",
        },
        resolver=lambda hostname: ["104.21.18.245"],
    )

    assert hosts == ["203.0.113.10", "203.0.113.11"]
