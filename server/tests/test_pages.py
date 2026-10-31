import pytest


@pytest.mark.parametrize("path,marker", [("/", "/ws/audience"), ("/screen", "/ws/screen")])
def test_pages_served_and_use_protocol_relative_ws(client, path, marker):
    r = client.get(path)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert marker in r.text and "wss" in r.text
