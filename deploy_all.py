import json
import os
import subprocess
import random

with open('credentials.json', 'r') as f:
    creds = json.load(f)

# Set AWS environment variables so boto3 automatically picks them up securely without saving to terminal history
os.environ['AWS_ACCESS_KEY_ID'] = creds['AWS_ACCESS_KEY_ID']
os.environ['AWS_SECRET_ACCESS_KEY'] = creds['AWS_SECRET_ACCESS_KEY']
os.environ['AWS_DEFAULT_REGION'] = creds['AWS_REGION']

# Generate a highly unique bucket name
bucket_name = f"lokesh-spotify-etl-lake-{random.randint(10000, 99999)}"
print(f"Assigning unique bucket name: {bucket_name}")

def run_step(cmd):
    print(f"\n--- Running: {' '.join(cmd)} ---")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR:\n{result.stderr}")
        exit(1)

# Execute the pipeline deployment steps
run_step(['python', 'infra/setup_s3.py', '--bucket-name', bucket_name])
run_step(['python', 'infra/setup_iam_roles.py'])
run_step(['python', 'infra/setup_lambda.py', '--bucket-name', bucket_name, '--client-id', creds['SPOTIFY_CLIENT_ID'], '--client-secret', creds['SPOTIFY_CLIENT_SECRET']])
run_step(['python', 'infra/setup_eventbridge.py'])
run_step(['python', 'infra/setup_glue_athena.py', '--bucket-name', bucket_name])

# Clean up secure credentials file now that deployment is complete
os.remove('credentials.json')
print("\n✅ Deployment completed! Credentials file has been securely deleted.")
