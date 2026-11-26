"""Regression tests for album release dates with mixed precision.

Spotify returns album.release_date as "YYYY", "YYYY-MM" or "YYYY-MM-DD". The original
code ran pd.to_datetime(..., errors="coerce") over the whole column; pandas inferred one
format from the first value and silently turned the others into nulls.
"""
import json

import awswrangler as wr
import pandas as pd

from conftest import BUCKET, s3_event

RAW_KEY = "raw_data/to_process/mixed_dates.json"


def _item(n, release_date):
    album_id = f"album{n:02d}"
    return {
        "added_at": "2026-01-01T00:00:00Z",
        "track": {
            "id": f"track{n:02d}", "name": f"Track {n}", "popularity": 50, "duration_ms": 200000,
            "album": {"id": album_id, "name": f"Album {n}", "release_date": release_date, "total_tracks": 10,
                      "external_urls": {"spotify": f"https://open.spotify.com/album/{album_id}"}},
            "artists": [{"id": f"artist{n:02d}", "name": f"Artist {n}",
                         "external_urls": {"spotify": "https://open.spotify.com/artist/x"}}],
        },
    }


def _albums_after_transform(transform_module, s3, release_dates):
    payload = {"items": [_item(i, d) for i, d in enumerate(release_dates)]}
    s3.put_object(Bucket=BUCKET, Key=RAW_KEY, Body=json.dumps(payload))
    transform_module.lambda_handler(s3_event(RAW_KEY), None)
    key = s3.list_objects_v2(Bucket=BUCKET, Prefix="transformed_data/albums/")["Contents"][0]["Key"]
    return wr.s3.read_parquet(f"s3://{BUCKET}/{key}").sort_values("album_id").reset_index(drop=True)


def test_mixed_precision_release_dates_are_not_lost(transform_module, s3):
    # Year-only value first: this is the order that made the old code null out the rest.
    albums = _albums_after_transform(transform_module, s3, ["2019", "2021-05", "2020-03-15", "1999-12-31"])

    # The raw Spotify string is kept unchanged.
    assert list(albums["album_release_date"]) == ["2019", "2021-05", "2020-03-15", "1999-12-31"]
    assert list(albums["album_release_date_precision"]) == ["year", "month", "day", "day"]
    # The parsed date is the first day of the period Spotify gave.
    assert list(albums["album_release_date_parsed"]) == [
        pd.Timestamp("2019-01-01"), pd.Timestamp("2021-05-01"),
        pd.Timestamp("2020-03-15"), pd.Timestamp("1999-12-31"),
    ]


def test_invalid_release_dates_become_null_without_affecting_others(transform_module, s3):
    albums = _albums_after_transform(transform_module, s3, ["0000", "not-a-date", "2020-02-30", "2018-07-04"])

    assert list(albums["album_release_date"]) == ["0000", "not-a-date", "2020-02-30", "2018-07-04"]
    assert albums["album_release_date_parsed"].isna().tolist() == [True, True, True, False]
    assert albums["album_release_date_parsed"].iloc[3] == pd.Timestamp("2018-07-04")


def test_no_release_dates_lost_on_synthetic_sample(transform_module, s3, sample_payload):
    s3.put_object(Bucket=BUCKET, Key=RAW_KEY, Body=json.dumps(sample_payload))
    transform_module.lambda_handler(s3_event(RAW_KEY), None)
    key = s3.list_objects_v2(Bucket=BUCKET, Prefix="transformed_data/albums/")["Contents"][0]["Key"]
    albums = wr.s3.read_parquet(f"s3://{BUCKET}/{key}")

    assert len(albums) == 40
    assert albums["album_release_date_parsed"].notna().sum() == 40
