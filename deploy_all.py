"""Deploy the whole pipeline by running the infra scripts in order.

AWS credentials come from the standard boto3 chain (AWS_PROFILE / SSO / `aws configure`, or
AWS_ACCESS_KEY_ID etc. in the environment). Nothing is read from a credentials file in the repo.
Spotify credentials come from SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET or a hidden prompt and are
passed to the child scripts through the environment, never as command-line arguments.
"""
import os
import random
import subprocess
import sys

import boto3

from infra.spotify_credentials import get_spotify_credentials


def run_step(cmd, env):
    print(f"\n--- Running: {' '.join(cmd)} ---")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=env)
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR:\n{result.stderr}")
        sys.exit(1)


def main():
    if not boto3.Session().region_name:
        sys.exit("ERROR: no AWS region configured. Set AWS_REGION / AWS_DEFAULT_REGION or a profile region.")

    client_id, client_secret = get_spotify_credentials()
    child_env = dict(os.environ, SPOTIFY_CLIENT_ID=client_id, SPOTIFY_CLIENT_SECRET=client_secret)

    bucket_name = f"lokesh-spotify-etl-lake-{random.randint(10000, 99999)}"
    print(f"Assigning unique bucket name: {bucket_name}")

    py = sys.executable
    run_step([py, 'infra/setup_s3.py', '--bucket-name', bucket_name], child_env)
    run_step([py, 'infra/setup_iam_roles.py', '--bucket-name', bucket_name], child_env)
    run_step([py, 'infra/setup_lambda.py', '--bucket-name', bucket_name], child_env)
    run_step([py, 'infra/setup_eventbridge.py'], child_env)
    run_step([py, 'infra/setup_glue_athena.py', '--bucket-name', bucket_name], child_env)
    print("\nDeployment completed.")


if __name__ == '__main__':
    main()
