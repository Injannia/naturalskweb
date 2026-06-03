from starlette.requests import Request

from app.utils.client_ip import get_client_ip


def _req(headers=None, client=("10.0.0.1", 0)):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": client,
    }
    return Request(scope)


def test_prefers_cf_connecting_ip():
    r = _req({"CF-Connecting-IP": "203.0.113.7", "X-Forwarded-For": "198.51.100.9"})
    assert get_client_ip(r) == "203.0.113.7"


def test_falls_back_to_xff_first_hop():
    r = _req({"X-Forwarded-For": "203.0.113.7, 70.41.3.18, 150.172.238.178"})
    assert get_client_ip(r) == "203.0.113.7"


def test_falls_back_to_socket_peer_without_proxy_headers():
    r = _req(client=("192.168.1.50", 1234))
    assert get_client_ip(r) == "192.168.1.50"


def test_no_client_returns_empty():
    r = _req(client=None)
    assert get_client_ip(r) == ""


def test_caps_at_45_chars():
    r = _req({"CF-Connecting-IP": "x" * 60})
    assert len(get_client_ip(r)) == 45
