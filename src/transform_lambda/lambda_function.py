import json
import re
import boto3
import pandas as pd
import awswrangler as wr
import os
import urllib.parse
from datetime import datetime

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
    return pd.DataFrame(artist_list).drop_duplicates(subset=['artist_id'])

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
            'artist_id': track.get('artists', [{}])[0].get('id'), # Primary artist
            'added_at': row.get('added_at')
        }
        track_list.append(track_element)
    return pd.DataFrame(track_list).drop_duplicates(subset=['track_id'])

def lambda_handler(event, context):
    try:
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        s3_key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
        
        # Ensure we're only processing raw data files
        if 'raw_data/to_process/' not in s3_key:
            print(f"Skipping key {s3_key}")
            return {'statusCode': 200, 'body': 'Skipped'}

        print(f"Processing s3://{bucket_name}/{s3_key}")
        
        # Read the JSON file from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        file_content = response['Body'].read().decode('utf-8')
        spotify_data = json.loads(file_content)
        
        items = spotify_data.get('items', [])
        
        # Transform data into distinct dataframes
        album_df = process_album(items)
        artist_df = process_artist(items)
        track_df = process_track(items)
        
        # Force column types to handle potential nulls gracefully during write
        # album_release_date stays a string; the parsed column already holds datetime objects or None.
        album_df['album_release_date_parsed'] = pd.to_datetime(album_df['album_release_date_parsed'])
        track_df['added_at'] = pd.to_datetime(track_df['added_at'], errors='coerce')

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        target_bucket = os.environ.get('TRANSFORMED_S3_BUCKET', bucket_name)
        
        # Write to S3 as Parquet using AWS Wrangler
        wr.s3.to_parquet(
            df=album_df,
            path=f"s3://{target_bucket}/transformed_data/albums/album_data_{timestamp}.parquet"
        )
        wr.s3.to_parquet(
            df=artist_df,
            path=f"s3://{target_bucket}/transformed_data/artists/artist_data_{timestamp}.parquet"
        )
        wr.s3.to_parquet(
            df=track_df,
            path=f"s3://{target_bucket}/transformed_data/tracks/track_data_{timestamp}.parquet"
        )
        
        # Move the raw file to a "processed" folder to avoid reprocessing
        copy_source = {'Bucket': bucket_name, 'Key': s3_key}
        processed_key = s3_key.replace('to_process/', 'processed/')
        
        s3_client.copy_object(CopySource=copy_source, Bucket=bucket_name, Key=processed_key)
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        
        print(f"Successfully processed {s3_key} and saved output to transformed_data/")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Data transformation successful'})
        }

    except Exception as e:
        print(f"Error processing data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
