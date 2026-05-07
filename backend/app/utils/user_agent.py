import re

_BROWSERS = [
    (re.compile(r"Firefox/(\d+)"), "Firefox"),
    (re.compile(r"Edg/(\d+)"), "Edge"),
    (re.compile(r"Chrome/(\d+)"), "Chrome"),
    (re.compile(r"Safari/(\d+)"), "Safari"),
]
_OS = [
    (re.compile(r"Windows"), "Windows"),
    (re.compile(r"Mac OS X|Macintosh"), "macOS"),
    (re.compile(r"Android"), "Android"),
    (re.compile(r"iPhone|iPad|iOS"), "iOS"),
    (re.compile(r"Linux"), "Linux"),
]


def parse_user_agent(ua: str) -> str:
    if not ua:
        return "Неизвестно"
    browser = None
    for rx, name in _BROWSERS:
        m = rx.search(ua)
        if m:
            browser = f"{name} {m.group(1)}"
            break
    os_name = None
    for rx, name in _OS:
        if rx.search(ua):
            os_name = name
            break
    if not browser and not os_name:
        return "Иное"
    parts = [p for p in (browser, os_name) if p]
    return " · ".join(parts)
