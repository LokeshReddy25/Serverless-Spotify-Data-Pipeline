import json

import pytest

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
