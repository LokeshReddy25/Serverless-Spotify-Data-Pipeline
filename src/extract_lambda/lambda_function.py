import base64
import datetime
import json
import logging
import os
import urllib.parse
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
DEFAULT_PLAYLIST_ID = '37i9dQZEVXbMDoHDwVN2tF'  # Top 50 Global
HTTP_TIMEOUT_SECONDS = 10
REQUIRED_ENV_VARS = ('SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET', 'S3_BUCKET_NAME')


def get_spotify_token(client_id, client_secret):
    auth_base64 = base64.b64encode(f"{client_id}:{client_secret}".encode('utf-8')).decode('utf-8')
    headers = {
        'Authorization': f'Basic {auth_base64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode('utf-8')

    req = urllib.request.Request(SPOTIFY_TOKEN_URL, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode('utf-8'))['access_token']


def extract_playlist_data(access_token, playlist_id):
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode('utf-8'))


def lambda_handler(event, context):
    """Fetch one playlist's tracks from Spotify and store the raw JSON in S3.

    Any failure is logged and re-raised, so Lambda records the invocation as failed
    instead of reporting success with an error body.
    """
    try:
        missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        bucket_name = os.environ['S3_BUCKET_NAME']
        playlist_id = os.environ.get('SPOTIFY_PLAYLIST_ID', DEFAULT_PLAYLIST_ID)

        access_token = get_spotify_token(os.environ['SPOTIFY_CLIENT_ID'], os.environ['SPOTIFY_CLIENT_SECRET'])
        logger.info("Spotify token retrieved.")

        spotify_data = extract_playlist_data(access_token, playlist_id)
        logger.info("Fetched playlist %s with %d items.", playlist_id, len(spotify_data.get('items', [])))

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        s3_key = f"raw_data/to_process/spotify_top_50_{timestamp}.json"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(spotify_data),
            ContentType='application/json'
        )
        logger.info("Uploaded raw data to s3://%s/%s", bucket_name, s3_key)
    except Exception:
        logger.exception("Spotify extraction failed.")
        raise

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Data extraction and upload successful', 's3_path': s3_key})
    }
