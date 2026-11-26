import json
import urllib.error

import pytest
from botocore.exceptions import ClientError

from conftest import BUCKET


@pytest.fixture
def stubbed_extract(extract_module, s3, sample_payload, monkeypatch):
    """Extract module with the two Spotify HTTP helpers replaced by stubs (no network)."""
    monkeypatch.setattr(extract_module, "get_spotify_token", lambda cid, secret: "stub-token")
    monkeypatch.setattr(extract_module, "extract_playlist_data", lambda token, pid: sample_payload)
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "stub-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "stub-value")
    monkeypatch.setenv("S3_BUCKET_NAME", BUCKET)
    return extract_module


def test_extract_writes_raw_json_to_s3(stubbed_extract, s3, sample_payload):
    result = stubbed_extract.lambda_handler({}, None)

    assert result["statusCode"] == 200
    key = json.loads(result["body"])["s3_path"]
    assert key.startswith("raw_data/to_process/spotify_top_50_") and key.endswith(".json")
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    assert json.loads(body) == sample_payload


def test_extract_uses_playlist_id_from_env(stubbed_extract, monkeypatch):
    seen = {}

    def fake_extract(token, pid):
        seen["pid"] = pid
        return {"items": []}

    monkeypatch.setattr(stubbed_extract, "extract_playlist_data", fake_extract)
    monkeypatch.setenv("SPOTIFY_PLAYLIST_ID", "customPlaylist123")
    stubbed_extract.lambda_handler({}, None)
    assert seen["pid"] == "customPlaylist123"


# ---------- error paths: the handler must raise (so Lambda records a failure), not return 500 ----------

def test_extract_raises_when_env_vars_missing(extract_module, s3, monkeypatch, caplog):
    monkeypatch.setenv("S3_BUCKET_NAME", BUCKET)  # client id and secret deliberately unset

    with pytest.raises(ValueError, match="SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET"):
        extract_module.lambda_handler({}, None)
    assert "Spotify extraction failed" in caplog.text


def test_extract_raises_on_spotify_http_error_and_writes_nothing(stubbed_extract, s3, monkeypatch, caplog):
    def fail(cid, secret):
        raise urllib.error.HTTPError("https://accounts.spotify.com/api/token", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(stubbed_extract, "get_spotify_token", fail)

    with pytest.raises(urllib.error.HTTPError):
        stubbed_extract.lambda_handler({}, None)
    assert "Spotify extraction failed" in caplog.text
    assert s3.list_objects_v2(Bucket=BUCKET).get("KeyCount") == 0


def test_extract_raises_when_bucket_missing(stubbed_extract, monkeypatch):
    monkeypatch.setenv("S3_BUCKET_NAME", "bucket-that-does-not-exist")

    with pytest.raises(ClientError, match="NoSuchBucket"):
        stubbed_extract.lambda_handler({}, None)


def test_extract_does_not_log_the_client_secret(stubbed_extract, monkeypatch, caplog):
    def fail(cid, secret):
        raise RuntimeError("token call failed")

    monkeypatch.setattr(stubbed_extract, "get_spotify_token", fail)
    with pytest.raises(RuntimeError):
        stubbed_extract.lambda_handler({}, None)
    assert "stub-value" not in caplog.text


def test_spotify_http_helpers_use_a_timeout(extract_module, monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url, timeout))
        return FakeResponse(b'{"access_token": "t", "items": []}')

    monkeypatch.setattr(extract_module.urllib.request, "urlopen", fake_urlopen)
    assert extract_module.get_spotify_token("id", "secret") == "t"
    assert extract_module.extract_playlist_data("t", "pl") == {"access_token": "t", "items": []}
    assert [t for _, t in calls] == [extract_module.HTTP_TIMEOUT_SECONDS] * 2
    assert calls[1][0] == "https://api.spotify.com/v1/playlists/pl/tracks"
