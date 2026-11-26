# Resume Claims vs. Code

Checked against commit `5148787` on 2026-11-26. "Code supports it" means the code does it. It does not mean there is evidence the code ran: **the repo has no logs, screenshots or outputs from AWS** (see `results/results.md`).

## Claim 1
> "Built an automated serverless pipeline that extracts trending data from the Spotify API using AWS Lambda and stores raw JSON in Amazon S3"

**Verdict: SUPPORTED in code, with two wording caveats.**

| Part | Evidence |
|---|---|
| Lambda calls the Spotify API (client-credentials token, then playlist tracks) | `src/extract_lambda/lambda_function.py:11-37` |
| Raw JSON stored in S3 at `raw_data/to_process/spotify_top_50_<timestamp>.json` | `src/extract_lambda/lambda_function.py:60-68` |
| "Automated": daily EventBridge rule targets this Lambda | `infra/setup_eventbridge.py:7, 18-48` |
| "Trending data" | The data is one playlist's tracks. By default that's `37i9dQZEVXbMDoHDwVN2tF`, commented "Top 50 Global" (`src/extract_lambda/lambda_function.py:45`). Nothing in the code computes trends. |

Caveats you should be ready for in an interview:
- **"Trending" is a stretch.** It's a snapshot of a chart playlist. Better: "daily snapshots of Spotify's Top 50 Global playlist".
- **Spotify API access.** On 27 Nov 2024 Spotify stopped serving algorithmic and Spotify-owned editorial playlists to new apps, and to development-mode apps without an approved extension (https://developer.spotify.com/blog/2024-11-27-changes-to-the-web-api). Top 50 Global is Spotify-owned. If your Spotify app was registered after that date, this call may have been refused. Only you know whether real data came through. `.gitignore` lists `push_mock_data.py` and `test_spotify_api.py`, which suggests mock data was used at some point. If it was, don't imply real data.
- Only the first page of results is fetched; there's no pagination (`lambda_function.py:28-37`). That's fine for a 50-track playlist.

## Claim 2
> "Transformed raw data into Parquet with AWS Data Wrangler, using AWS Glue for schema discovery and Amazon Athena for serverless SQL analytics"

**Verdict: PARTIAL.**

| Part | Status | Evidence |
|---|---|---|
| Raw JSON → Parquet with AWS Data Wrangler | SUPPORTED | `src/transform_lambda/lambda_function.py:93-104` (`wr.s3.to_parquet`, 3 tables, default Snappy codec, confirmed locally in `results/raw/bench_pipeline_50.json`). Runs automatically from an S3 `ObjectCreated` event (`infra/setup_lambda.py:59-96`). |
| Glue for schema discovery | PARTIAL | **It's a Glue crawler**, created by Boto3 (`infra/setup_glue_athena.py:52-74`) and pointed at `s3://<bucket>/transformed_data/`. The code **never starts it** and gives it no schedule; it prints "run the crawler from the AWS Console" (`:76`). Data Wrangler does **not** write to the Glue Catalog: `to_parquet` is called without `dataset=True`, `database=` or `table=`. |
| Athena for SQL analytics | PARTIAL / weak | `athena_client` is created but never used (`infra/setup_glue_athena.py:8`). There's no workgroup, no query-result location and no saved queries. The only Athena artifact is one example query in the README. |

Data-quality issue you should know about: `pd.to_datetime(..., errors='coerce')` on `album_release_date` (`lambda_function.py:86`) **lost 36 of 40 dates** in the local synthetic test, because Spotify mixes `YYYY` and `YYYY-MM-DD` formats (`results/raw/derived_metrics_50.txt`). It was tested only with pandas 3.1.1.

## Claim 3
> "Automated daily processing and infrastructure setup with EventBridge, IAM, and Boto3, enabling repeatable deployment of the full pipeline"

**Verdict: PARTIAL.**

| Part | Status | Evidence |
|---|---|---|
| Daily schedule via EventBridge | SUPPORTED for extraction | `cron(0 12 * * ? *)`, daily at 12:00 UTC, targets `SpotifyExtractData` (`infra/setup_eventbridge.py:7, 56`). The transform is run by an **S3 event, not EventBridge**. The Glue crawler is **not** scheduled. |
| Infrastructure created by code (not the console) | SUPPORTED | Boto3 scripts create the S3 bucket and prefixes (`infra/setup_s3.py`), IAM roles (`infra/setup_iam_roles.py`, `infra/setup_glue_athena.py:25-50`), both Lambdas and the S3 trigger (`infra/setup_lambda.py`), the EventBridge rule (`infra/setup_eventbridge.py`), and the Glue database and crawler. `deploy_all.py` runs them in order. **No Terraform or CloudFormation.** |
| IAM | SUPPORTED, but not least-privilege | Every role gets `AmazonS3FullAccess` (`infra/setup_iam_roles.py:47, 55`; `infra/setup_glue_athena.py:49`). The code's own comment says "Simplified for development, should be scoped down in prod". |
| "Repeatable deployment" | PARTIAL | Most steps handle "already exists", but: (a) `deploy_all.py:15` picks a **random bucket name on every run**, so a rerun creates a new bucket and leaves the old one behind; (b) there's no teardown script and no state tracking, unlike Terraform or CloudFormation; (c) the region fallback is inconsistent (`setup_s3.py:49` defaults to `us-east-1`, `setup_lambda.py:125` to `ap-south-1`; `deploy_all.py` avoids this by setting the region); (d) the Lambda layer ARN is pinned to version 14 (`setup_lambda.py:126`); (e) updating an existing Lambda doesn't update its role or layers (`setup_lambda.py:42-57`). |
| "Full pipeline" | PARTIAL | Starting the crawler and setting up Athena are manual steps (see Claim 2) |

## Things you could not defend in an interview as currently written

1. **Any number** about records, run counts, latency, data volume or cost. None was measured on AWS and no evidence is saved.
2. **"Least-privilege" or "granular" IAM**, which the current README states. The code attaches `AmazonS3FullAccess` everywhere.
3. **"Glue for schema discovery"** unless you actually ran the crawler from the console and can describe the tables it produced.
4. **"Trending data"** as if it were analysis. It's a playlist snapshot.
5. **Error handling.** Both handlers catch every exception and **return** a 500 instead of raising it (`extract …:77-82`, `transform …:120-125`). Lambda then records the invocation as successful, so failures don't trigger retries or error metrics.
6. **Secrets handling.** The Spotify client secret is passed as a command-line argument (`deploy_all.py:29`) and stored as a plain-text Lambda environment variable (`infra/setup_lambda.py:116-120`). `deploy_all.py` also expects long-lived AWS access keys in `credentials.json`. No secret was committed (`results/raw/secret_scan.txt`), but expect the question "why not Secrets Manager or SSM?"

## Suggested wording (only what the code supports)

- "Built a serverless ETL pipeline on AWS: an EventBridge-scheduled Python Lambda pulls daily snapshots of Spotify's Top 50 Global playlist through the Spotify Web API and stores the raw JSON in Amazon S3."
- "Wrote an S3-event-triggered Lambda that uses pandas and AWS Data Wrangler (AWS SDK for pandas) to normalise the JSON into album, artist and track tables stored as Snappy-compressed Parquet. Set up a Glue crawler and Data Catalog database so the tables can be queried in Amazon Athena."
- "Wrote Boto3 deployment scripts that create the S3 bucket, IAM roles, Lambda functions, S3 trigger, EventBridge schedule and Glue crawler from one command."

Only if you actually did it, you can add: "ran the Glue crawler and queried the tables in Athena". Avoid "least-privilege", "repeatable infrastructure as code" and any metric until you have evidence.
