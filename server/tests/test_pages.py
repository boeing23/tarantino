import pytest


@pytest.mark.parametrize("path,role", [("/", "audience"), ("/screen", "screen")])
def test_pages_served_and_connect_as_role(client, path, role):
    r = client.get(path)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert f'live("{role}"' in r.text


def test_live_js_uses_wss_behind_https(client):
    js = client.get("/static/live.js").text
    assert "wss" in js and "/ws/${role}" in js


@pytest.mark.parametrize("path", ["/", "/screen"])
def test_pages_use_vendored_assets_not_cdn(client, path):
    html = client.get(path).text
    assert "/static/vendor/daisyui.css" in html and "/static/vendor/alpine.js" in html
    assert "cdn." not in html and "unpkg" not in html


def test_vendored_assets_served_gzipped(client):
    r = client.get("/static/vendor/daisyui.css", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["content-encoding"] == "gzip"


def test_audience_page_is_mobile_ready(client):
    assert 'name="viewport"' in client.get("/").text
