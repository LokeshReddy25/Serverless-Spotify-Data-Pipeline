import json

import awswrangler as wr
import pytest
from botocore.exceptions import ClientError

from conftest import BUCKET, s3_event

RAW_KEY = "raw_data/to_process/spotify_top_50_2026-01-01_12-00-00.json"


@pytest.fixture
def raw_object(s3, sample_payload):
    s3.put_object(Bucket=BUCKET, Key=RAW_KEY, Body=json.dumps(sample_payload))
    return RAW_KEY


def _keys(s3, prefix):
    return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])]


def test_transform_writes_three_parquet_tables(transform_module, s3, raw_object):
    result = transform_module.lambda_handler(s3_event(raw_object), None)

    assert result["statusCode"] == 200
    rows = {}
    for key in _keys(s3, "transformed_data/"):
        table = key.split("/")[1]
        rows[table] = len(wr.s3.read_parquet(f"s3://{BUCKET}/{key}"))
    # synthetic sample: 50 tracks, 40 unique albums, 35 unique artists
    assert rows == {"albums": 40, "artists": 35, "tracks": 50}


def test_transform_moves_raw_file_to_processed(transform_module, s3, raw_object):
    transform_module.lambda_handler(s3_event(raw_object), None)

    assert _keys(s3, "raw_data/to_process/") == []
    assert _keys(s3, "raw_data/processed/") == [RAW_KEY.replace("to_process/", "processed/")]


def test_transform_skips_keys_outside_raw_prefix(transform_module, s3):
    result = transform_module.lambda_handler(s3_event("somewhere_else/file.json"), None)

    assert result["statusCode"] == 200
    assert _keys(s3, "transformed_data/") == []


def test_transform_decodes_url_encoded_keys(transform_module, s3, sample_payload):
    key = "raw_data/to_process/spotify top 50.json"
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(sample_payload))

    result = transform_module.lambda_handler(s3_event("raw_data/to_process/spotify+top+50.json"), None)

    assert result["statusCode"] == 200
    assert len(_keys(s3, "transformed_data/")) == 3


# ---------- error paths: the handler must raise (so Lambda records a failure), not return 500 ----------

def test_transform_raises_when_object_missing(transform_module, s3, caplog):
    with pytest.raises(ClientError, match="NoSuchKey"):
        transform_module.lambda_handler(s3_event("raw_data/to_process/missing.json"), None)
    assert "Transform failed" in caplog.text


def test_transform_raises_on_invalid_json_and_keeps_raw_file(transform_module, s3):
    s3.put_object(Bucket=BUCKET, Key=RAW_KEY, Body=b"{not json")

    with pytest.raises(json.JSONDecodeError):
        transform_module.lambda_handler(s3_event(RAW_KEY), None)
    # The raw file stays in to_process/ so it can be retried; nothing is written.
    assert _keys(s3, "raw_data/to_process/") == [RAW_KEY]
    assert _keys(s3, "transformed_data/") == []


def test_transform_raises_on_payload_without_tracks(transform_module, s3):
    s3.put_object(Bucket=BUCKET, Key=RAW_KEY, Body=json.dumps({"items": [{"track": None}]}))

    with pytest.raises(ValueError, match="No track items"):
        transform_module.lambda_handler(s3_event(RAW_KEY), None)
    assert _keys(s3, "raw_data/to_process/") == [RAW_KEY]


def test_transform_raises_on_malformed_event(transform_module, s3):
    with pytest.raises(KeyError):
        transform_module.lambda_handler({"not": "an s3 event"}, None)


def test_transform_raises_when_parquet_write_fails_and_keeps_raw_file(transform_module, s3, raw_object,
                                                                      monkeypatch):
    def broken_write(**kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(transform_module.wr.s3, "to_parquet", broken_write)
    with pytest.raises(RuntimeError, match="simulated write failure"):
        transform_module.lambda_handler(s3_event(raw_object), None)
    assert _keys(s3, "raw_data/to_process/") == [RAW_KEY]
