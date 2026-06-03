from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    """Real client IP, correct behind the Cloudflare Tunnel.

    In production the app is reachable ONLY through cloudflared (no published
    ports), so `request.client.host` is always the internal cloudflared peer —
    identical for every visitor. The real visitor IP arrives in the proxy
    headers Cloudflare sets at the edge, which are trustworthy here precisely
    because no client can reach the origin directly to forge them.

    Order: Cloudflare's `CF-Connecting-IP` → first `X-Forwarded-For` hop →
    the direct socket peer (local/dev, no proxy). Capped at 45 chars to match
    the `ip_address` column (IPv6-safe).
    """
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()[:45]

    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:45]

    return request.client.host if request.client else ""
