import json
import logging
import os
import re
import urllib.parse
from datetime import datetime

import awswrangler as wr
import boto3
import pandas as pd

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

# Spotify gives album.release_date at one of three precisions. Each is parsed with its own
# format, so one precision can never cause values of another precision to be dropped.
_RELEASE_DATE_FORMATS = (
    ('day', re.compile(r'\d{4}-\d{2}-\d{2}'), '%Y-%m-%d'),
    ('month', re.compile(r'\d{4}-\d{2}'), '%Y-%m'),
    ('year', re.compile(r'\d{4}'), '%Y'),
)

ALBUM_COLUMNS = ['album_id', 'album_name', 'album_release_date', 'album_release_date_precision',
                 'album_release_date_parsed', 'album_total_tracks', 'album_url']


def parse_release_date(value):
    """Parse a Spotify release date ("YYYY", "YYYY-MM" or "YYYY-MM-DD").

    Returns (date, precision). Year and month precision are anchored to the first day of
    that period. Values that don't match, or aren't real dates (e.g. "0000"), return (None, None).
    """
    if not isinstance(value, str):
        return None, None
    value = value.strip()
    for precision, pattern, fmt in _RELEASE_DATE_FORMATS:
        if pattern.fullmatch(value):
            try:
                return datetime.strptime(value, fmt), precision
            except ValueError:
                return None, None
    return None, None


def process_album(items):
    album_list = []
    for row in items:
        track = row.get('track', {})
        if not track:
            continue
        album = track.get('album', {})
        raw_release_date = album.get('release_date')
        parsed_release_date, precision = parse_release_date(raw_release_date)
        album_element = {
            'album_id': album.get('id'),
            'album_name': album.get('name'),
            'album_release_date': raw_release_date,  # raw Spotify string, kept unchanged
            'album_release_date_precision': precision,
            'album_release_date_parsed': parsed_release_date,
            'album_total_tracks': album.get('total_tracks'),
            'album_url': album.get('external_urls', {}).get('spotify')
        }
        album_list.append(album_element)
    return pd.DataFrame(album_list, columns=ALBUM_COLUMNS).drop_duplicates(subset=['album_id'])


ARTIST_COLUMNS = ['artist_id', 'artist_name', 'artist_url']
TRACK_COLUMNS = ['track_id', 'track_name', 'track_popularity', 'track_duration_ms', 'album_id', 'artist_id',
                 'added_at']
RAW_PREFIX = 'raw_data/to_process/'
PROCESSED_PREFIX = 'raw_data/processed/'


def process_artist(items):
    artist_list = []
    for row in items:
        track = row.get('track', {})
        if not track:
            continue
        for artist in track.get('artists', []):
            artist_element = {
                'artist_id': artist.get('id'),
                'artist_name': artist.get('name'),
                'artist_url': artist.get('external_urls', {}).get('spotify')
            }
            artist_list.append(artist_element)
    return pd.DataFrame(artist_list, columns=ARTIST_COLUMNS).drop_duplicates(subset=['artist_id'])


def process_track(items):
    track_list = []
    for row in items:
        track = row.get('track', {})
        if not track:
            continue
        track_element = {
            'track_id': track.get('id'),
            'track_name': track.get('name'),
            'track_popularity': track.get('popularity'),
            'track_duration_ms': track.get('duration_ms'),
            'album_id': track.get('album', {}).get('id'),
            'artist_id': (track.get('artists') or [{}])[0].get('id'),  # primary artist
            'added_at': row.get('added_at')
        }
        track_list.append(track_element)
    return pd.DataFrame(track_list, columns=TRACK_COLUMNS).drop_duplicates(subset=['track_id'])


def transform_object(bucket_name, s3_key):
    """Transform one raw JSON object into three Parquet tables, then move it to processed/.

    The raw file is moved only after all three tables are written, so a failure leaves it in
    to_process/ where it can be retried.
    """
    logger.info("Processing s3://%s/%s", bucket_name, s3_key)
    response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
    spotify_data = json.loads(response['Body'].read().decode('utf-8'))

    items = spotify_data.get('items', [])
    track_df = process_track(items)
    if track_df.empty:
        raise ValueError(f"No track items found in s3://{bucket_name}/{s3_key}")
    album_df = process_album(items)
    artist_df = process_artist(items)

    # album_release_date stays a string; the parsed column already holds datetime objects or None.
    album_df['album_release_date_parsed'] = pd.to_datetime(album_df['album_release_date_parsed'])
    track_df['added_at'] = pd.to_datetime(track_df['added_at'], errors='coerce')

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target_bucket = os.environ.get('TRANSFORMED_S3_BUCKET', bucket_name)
    for table, df in (('albums', album_df), ('artists', artist_df), ('tracks', track_df)):
        wr.s3.to_parquet(
            df=df,
            path=f"s3://{target_bucket}/transformed_data/{table}/{table[:-1]}_data_{timestamp}.parquet"
        )

    processed_key = s3_key.replace(RAW_PREFIX, PROCESSED_PREFIX, 1)
    s3_client.copy_object(CopySource={'Bucket': bucket_name, 'Key': s3_key}, Bucket=bucket_name, Key=processed_key)
    s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
    logger.info("Processed %s (%d tracks) and moved it to %s", s3_key, len(track_df), processed_key)
    return processed_key


def lambda_handler(event, context):
    """Handle an S3 ObjectCreated event for raw_data/to_process/*.json.

    Any failure is logged and re-raised, so Lambda records the invocation as failed
    instead of reporting success with an error body.
    """
    processed, skipped = [], []
    try:
        for record in event['Records']:
            bucket_name = record['s3']['bucket']['name']
            s3_key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8')
            if not s3_key.startswith(RAW_PREFIX):
                logger.info("Skipping key outside %s: %s", RAW_PREFIX, s3_key)
                skipped.append(s3_key)
                continue
            processed.append(transform_object(bucket_name, s3_key))
    except Exception:
        logger.exception("Transform failed.")
        raise

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Data transformation successful', 'processed': processed,
                            'skipped': skipped})
    }
