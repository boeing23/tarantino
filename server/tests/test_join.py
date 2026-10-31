import pytest

from app.join import resolve_join_url


@pytest.mark.parametrize("public,tunnel,request_url,lan,expected", [
    ("https://show.example.com", "abc.trycloudflare.com", "http://localhost:8000/", "http://10.0.0.5:8000", "https://show.example.com/"),
    ("", "abc.trycloudflare.com", "http://localhost:8000/", "http://10.0.0.5:8000", "https://abc.trycloudflare.com/"),
    ("", None, "http://192.168.1.4:8000/", "http://10.0.0.5:8000", "http://192.168.1.4:8000/"),
    ("", None, "http://localhost:8000/", "http://10.0.0.5:8000", "http://10.0.0.5:8000/"),
    ("", None, "http://127.0.0.1:8000/", "", "http://127.0.0.1:8000/"),
])
def test_resolve_join_url(public, tunnel, request_url, lan, expected):
    assert resolve_join_url(public, tunnel, request_url, lan) == expected
