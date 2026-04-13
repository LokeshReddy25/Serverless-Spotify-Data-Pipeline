import json
import os
import datetime
import urllib.request
import urllib.parse
import base64
import boto3

s3_client = boto3.client('s3')

def get_spotify_token(client_id, client_secret):
    token_url = 'https://accounts.spotify.com/api/token'
    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = auth_string.encode('utf-8')
    auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    headers = {
        'Authorization': f'Basic {auth_base64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode('utf-8')
    
    req = urllib.request.Request(token_url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req) as response:
        response_data = json.loads(response.read().decode('utf-8'))
        return response_data['access_token']

def extract_playlist_data(access_token, playlist_id):
    # API Endpoint for a playlist's tracks
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def lambda_handler(event, context):
    try:
        # Load environment variables
        client_id = os.environ.get('SPOTIFY_CLIENT_ID')
        client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        playlist_id = os.environ.get('SPOTIFY_PLAYLIST_ID', '37i9dQZEVXbMDoHDwVN2tF') # Default: Top 50 Global
        
        if not all([client_id, client_secret, bucket_name]):
            raise ValueError("Missing essential environment variables: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, or S3_BUCKET_NAME.")
        
        # 1. Authenticate with Spotify
        get_token_start = datetime.datetime.now()
        access_token = get_spotify_token(client_id, client_secret)
        print(f"Token retrieved successfully.")

        # 2. Extract Data
        spotify_data = extract_playlist_data(access_token, playlist_id)
        print(f"Data extracted for playlist: {playlist_id}")
        
        # 3. Store raw data in S3
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        s3_key = f"raw_data/to_process/spotify_top_50_{timestamp}.json"
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(spotify_data),
            ContentType='application/json'
        )
        
        print(f"Successfully uploaded raw data to s3://{bucket_name}/{s3_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Data extraction and upload successful', 's3_path': s3_key})
        }
        
    except Exception as e:
        print(f"Error extracting data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
