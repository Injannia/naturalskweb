from unittest.mock import MagicMock

from app.utils.user_agent import parse_user_agent
from app.utils.system_info import get_tool_versions


def test_parse_user_agent_chrome_linux():
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    assert parse_user_agent(ua) == "Chrome 120 · Linux"


def test_parse_user_agent_firefox_windows():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
    assert parse_user_agent(ua) == "Firefox 121 · Windows"


def test_parse_user_agent_unknown():
    assert parse_user_agent("") == "Неизвестно"
    assert parse_user_agent("curl/8.0") == "Иное"


def test_get_tool_versions_caches(monkeypatch):
    calls = {"n": 0}

    def fake_run(*args, **kwargs):
        calls["n"] += 1
        result = MagicMock()
        result.stdout = "Python 3.12.3\n"
        result.returncode = 0
        return result

    monkeypatch.setattr("subprocess.run", fake_run)
    from app.utils import system_info

    system_info._cache = None
    system_info._cache_at = 0.0
    v1 = get_tool_versions()
    v2 = get_tool_versions()
    assert v1 == v2
    assert calls["n"] == 2  # ffmpeg + yt-dlp called once (python uses sys.version)
