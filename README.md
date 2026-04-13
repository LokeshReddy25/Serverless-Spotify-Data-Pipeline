# 🎵 Serverless Spotify Data Pipeline

This repository contains an end-to-end data engineering pipeline deployed entirely on AWS using serverless architectures. It extracts top global music tracks from Spotify, triggers an automated transformation task leveraging AWS Data Wrangler, and organizes the resulting data in S3 for SQL analytics with Amazon Athena.

## 🏗️ Architecture
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Spotify API  │────▶│ Lambda       │────▶│ S3 Raw/      │────▶│ Lambda       │
│ (Daily Top)  │     │ (Extractor)  │     │ (JSON Store) │     │ (Transformer)│
└──────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                      │
                                                               ┌──────▼───────┐
                                                               │ S3 Parquet/  │
                                                               │ (Optimized)  │
                                                               └──────┬───────┘
                                                                      │
                                                               ┌──────▼───────┐
                                                               │ Glue/Athena  │
                                                               │ (SQL Query)  │
                                                               └──────────────┘
```

## 🛠️ AWS Services Used
| Service | Role |
| :--- | :--- |
| **Amazon S3** | Data lake storage for both raw JSON and optimized Parquet datasets |
| **AWS Lambda** | Python functions for API extraction and data transformation (AWS Wrangler) |
| **AWS Glue** | Data Catalog and Crawler for automatic schema discovery |
| **Amazon Athena** | Serverless SQL engine for querying transformed parquet data |
| **EventBridge** | Scheduled daily triggers for automated data extraction |
| **AWS IAM** | Granular security policies and execution roles for all services |

## 📂 Project Structure
```text
├── README.md                          # Project documentation
├── deploy_all.py                      # Orchestration script for full deployment
├── credentials.json                   # (Created locally) API & AWS credentials
├── infra/                             # Infrastructure setup scripts (Boto3)
│   ├── setup_s3.py                    # Step 1: Create S3 bucket & folder structure
│   ├── setup_iam_roles.py             # Step 2: Provision least-privilege IAM roles
│   ├── setup_lambda.py                # Step 3: Deploy & configure Lambda functions
│   ├── setup_eventbridge.py           # Step 4: Schedule daily automated runs
│   └── setup_glue_athena.py           # Step 5: Setup Catalog, Crawler & Athena
└── src/                               # Lambda Source Code
    ├── extract_lambda/                # Spotify API extraction logic
    └── transform_lambda/              # Data Wrangler Parquet transformation
```

## 🚀 Quick Start

### 1. Prerequisites
*   AWS CLI configured (`aws configure`)
*   Spotify Developer App (`client_id` & `client_secret`)
*   Python 3.9+ with `boto3` installed

### 2. Auto Deployment
The easiest way to deploy is using the master script:
1. Create a `credentials.json` with your AWS and Spotify keys.
2. Run the deployment:
```bash
python deploy_all.py
```

### 3. Manual Deployment (Step-by-Step)
If you prefer running individual components:
```bash
# Create storage
python infra/setup_s3.py --bucket-name YOUR_BUCKET_NAME

# Setup Permissions
python infra/setup_iam_roles.py

# Deploy Code
python infra/setup_lambda.py --bucket-name BUCKET --client-id ID --client-secret SECRET

# Setup Orchestration & Analytics
python infra/setup_eventbridge.py
python infra/setup_glue_athena.py --bucket-name BUCKET
```

## 📊 Analytics
Once the pipeline has run, you can immediately query the data in **Amazon Athena**:

```sql
-- Top 10 Most Popular Tracks
SELECT 
  t.track_name, 
  ar.artist_name, 
  al.album_name, 
  t.track_popularity
FROM "spotify_db"."tracks" t
JOIN "spotify_db"."artists" ar ON t.artist_id = ar.artist_id
JOIN "spotify_db"."albums" al ON t.album_id = al.album_id
ORDER BY t.track_popularity DESC
LIMIT 10;
```

## 📝 Copyright & License
Copyright (c) 2026 Lokesh Reddy. All Rights Reserved.

This repository is provided strictly for viewing and portfolio display purposes only. You are not granted permission to download, use, copy, modify, distribute, or create derivative works from this code.
