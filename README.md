# Serverless Spotify Data Pipeline

This repository contains an end-to-end data engineering pipeline deployed entirely on AWS using serverless architectures. 
It extracts top global music tracks from Spotify, triggers an automated transformation task leveraging AWS Data Wrangler, and organizes the resulting data in S3 for SQL analytics with Amazon Athena.

## Project Structure
- `src/extract_lambda/`: Lambda function retrieving Spotify API data.
- `src/transform_lambda/`: Lambda function taking raw S3 data and transforming into Parquet datasets.
- `infra/`: AWS provisioning scripts using Boto3.

## Deployment Instructions

### Prerequisites
1. Set up an AWS account and configure your AWS CLI on your local machine (`aws configure`).
2. Add your Spotify Developer Keys to a Spotify Dashboard app to get your `client_id` and `client_secret`.
3. Make sure you have python installed and set up `boto3`.

### 1. Provision Infrastructure & Lambdas

Run the scripts in the `infra` folder in this exact sequence to build up your stack. (Replace `YOUR_UNIQUE_BUCKET_NAME` with a unique text string e.g., `spotify-etl-bucket-lokesh123`).

```bash
# 1. Create S3 Bucket and Folders
python infra/setup_s3.py --bucket-name YOUR_UNIQUE_BUCKET_NAME

# 2. Setup IAM Roles
python infra/setup_iam_roles.py

# 3. Deploy the Lambdas and configure the S3 trigger
python infra/setup_lambda.py --bucket-name YOUR_UNIQUE_BUCKET_NAME --client-id YOUR_SPOTIFY_CLIENT_ID --client-secret YOUR_SPOTIFY_CLIENT_SECRET
```

### 2. Orchestration & Analytics

```bash
# 4. Attach EventBridge scheduled trigger for daily automated runs
python infra/setup_eventbridge.py

# 5. Create the Glue Database & Crawler
python infra/setup_glue_athena.py --bucket-name YOUR_UNIQUE_BUCKET_NAME
```

### 3. Verification

- Head to the **Lambda** console in AWS and manually test your `SpotifyExtractData` function to kick off the pipeline immediately.
- Go to the **S3** console and verify files have landed in `raw_data/processed/` and `transformed_data/` folders.
- Finally, open **Amazon Athena** and run standard SQL queries against the newly populated Spotify tables!
