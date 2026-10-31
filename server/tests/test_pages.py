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


@pytest.mark.parametrize("path", ["/", "/screen"])
def test_pages_load_bible_and_handle_reset(client, path):
    html = client.get(path).text
    assert 'fetch("/show")' in html and "reset:" in html


def test_screen_video_starts_muted_so_autoplay_is_allowed(client):
    html = client.get("/screen").text
    video = html[html.index("<video"):html.index("</video>")]
    assert " muted " in video and "$el.muted = !soundOn" in video and "$el.play()" in video


@pytest.mark.parametrize("path", ["/", "/screen", "/static/live.js"])
def test_pages_are_revalidated_so_updates_reach_browsers(client, path):
    assert client.get(path).headers["cache-control"] == "no-cache"
