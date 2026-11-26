# Resume Claims vs. Code

## Current status: refreshed 2026-11-26 against `main` at `d6afb68`

This refresh covers everything merged since the first check (PRs #1–#4): the date-bug fix and tests, error handling, scoped IAM, teardown, the Athena workgroup and crawler step, CI, the Python compatibility matrix, and the move to the `python3.14` runtime with a documented, configurable layer ARN.

**How to read the verdicts.** **SUPPORTED** means the current code does it *and* that was verified locally: by the test suite against moto (an in-memory AWS mock), with Spotify stubbed. **Nothing has been deployed to AWS since the original account was lost**, so no verdict means "proven on AWS". Every AWS measurement stays **NOT MEASURED** (see `results/results.md`).

Local test evidence for this refresh: 81 tests, 81 passed, 91% coverage, flake8 clean, in each of Python 3.11.9 (dev pins), Python 3.14.10 + pandas 3.0.6, and Python 3.14.10 + pandas 3.1.1 (`results/raw/claims_refresh_tests_*.txt`). CI passed on GitHub on pull requests #2, #3 and #4, as observed on the pull request pages on 2026-11-26; no CI logs are saved in this repository.

| Claim | Verdict at `5148787` | Verdict now | Change |
|---|---|---|---|
| 1. Lambda extracts Spotify data → raw JSON in S3 | SUPPORTED (code only) | **SUPPORTED** | Now also verified locally |
| 2. Parquet via Data Wrangler; Glue schema discovery; Athena SQL | PARTIAL | **PARTIAL** | Glue and Athena setup is now in code and verified in moto, but schema discovery and queries have never run |
| 3. Daily automation; infrastructure setup with EventBridge, IAM and Boto3; repeatable deployment | PARTIAL | **SUPPORTED in code (verified in moto only; never deployed to AWS)** | Fixed bucket name, redeploy and teardown, scoped IAM; all verified in moto. "Full pipeline" includes the Glue crawler and Athena steps, which have never run: no crawl has produced tables and no Athena query has been executed (see Claim 2). |

### Claim 1
> "Built an automated serverless pipeline that extracts trending data from the Spotify API using AWS Lambda and stores raw JSON in Amazon S3"

**Verdict: SUPPORTED** (code, and verified locally).

| Part | Code | Local verification |
|---|---|---|
| Lambda calls the Spotify API (client-credentials token, playlist tracks, 10 s timeout) | `src/extract_lambda/lambda_function.py:22-39` | `tests/test_extract.py::test_spotify_http_helpers_use_a_timeout`; the HTTP calls themselves are stubbed |
| Raw JSON stored in S3 at `raw_data/to_process/` | `src/extract_lambda/lambda_function.py:63-69` | `tests/test_extract.py:21` `test_extract_writes_raw_json_to_s3` (moto S3) |
| "Automated": daily EventBridge rule targets the extract Lambda | `infra/config.py:14`, `infra/setup_eventbridge.py:12-22` | `tests/test_deployment.py:58` checks the rule's schedule and target |
| Failures are recorded as failures | `src/extract_lambda/lambda_function.py:72-73` (log and re-raise) | `tests/test_extract.py:46`, `:54`, `:66` |

Caveats, unchanged from the first check:
- **"Trending" overstates it.** It's a daily snapshot of one playlist (default Top 50 Global, `src/extract_lambda/lambda_function.py:17`).
- **Spotify API access.** Since 27 Nov 2024, new Spotify apps (and development-mode apps without an approved extension) may not be able to read Spotify-owned editorial playlists such as Top 50 Global. There is no saved evidence in this repository of the code running against the real Spotify API.
- Only the first page of results is fetched.

### Claim 2
> "Transformed raw data into Parquet with AWS Data Wrangler, using AWS Glue for schema discovery and Amazon Athena for serverless SQL analytics"

**Verdict: PARTIAL** (improved since `5148787`).

| Part | Status | Code | Local verification |
|---|---|---|---|
| Raw JSON → Parquet with AWS Data Wrangler | **SUPPORTED** | `src/transform_lambda/lambda_function.py:111-145` (`wr.s3.to_parquet`, 3 tables) | `tests/test_transform.py:22` reads back 40/35/50 rows from moto S3; release dates kept for every precision (`tests/test_release_dates.py:39`). Tests pass with the Lambda layer's verified awswrangler 3.18.0 and pyarrow 24.0.0 on Python 3.14. |
| Glue for schema discovery | **PARTIAL** | Crawler created by `infra/setup_glue_athena.py:16-38`; one-command start in `infra/run_crawler.py:16-45`; optional `deploy_all.py --run-crawler` | moto checks that the crawler is created and that the start call is made (`tests/test_glue_athena.py:75`). moto can't actually crawl, so **schema discovery itself has never been observed**. |
| Athena for SQL analytics | **PARTIAL** | Workgroup with result location and a 1 GiB scan limit: `infra/setup_glue_athena.py:55-76` | moto checks the workgroup settings (`tests/test_glue_athena.py:23`). **No Athena query has been run**; the README's SQL is an example. |

What would move this to SUPPORTED: deploying to an AWS account, running the crawler, and saving the crawler output and an Athena query result (with its "data scanned" figure) in `results/`.

### Claim 3
> "Automated daily processing and infrastructure setup with EventBridge, IAM, and Boto3, enabling repeatable deployment of the full pipeline"

**Verdict: SUPPORTED in code (verified in moto only; never deployed to AWS).** Was PARTIAL at `5148787`. "Full pipeline" includes the Glue crawler and Athena steps, which have never run: no crawl has produced tables and no Athena query has been executed (see Claim 2).

| Part | Code | Local verification |
|---|---|---|
| Daily processing via EventBridge | `infra/setup_eventbridge.py:12-22` (rule + target, default `cron(0 12 * * ? *)`). The transform runs on the S3 event, as before. | `tests/test_deployment.py:58` |
| Infrastructure created by Boto3 code | `deploy_all.py:21-47` calls the S3, IAM, Lambda, EventBridge and Glue/Athena setup functions in order | `tests/test_deployment.py:58` checks that every resource exists after one deploy |
| IAM | Bucket- and prefix-scoped inline policies, with no `AmazonS3FullAccess` (`infra/setup_iam_roles.py:52-76`; detached from old roles at `:102-103`) | `tests/test_iam_roles.py:41`, `:79` check the policy documents. moto doesn't enforce IAM, so **whether these permissions are enough on AWS is untested**. |
| Repeatable deployment | Fixed, validated bucket name (`infra/config.py:39`); updates in place on rerun; documented per-region layer ARN with override (`infra/config.py:62`); Lambda runtime `python3.14` (`infra/config.py:26`) | `tests/test_deployment.py:103` (redeploy updates in place), `:204` (teardown removes everything deploy created), `:231` (teardown safe to rerun); `tests/test_lambda_layers.py` (layer ARN selection and rejections) |
| "Full pipeline" | Deploy now also creates the Glue crawler and the Athena workgroup; starting the crawler is one command | Creation of both is verified in moto, but **the crawler has never run and no Athena query has been executed** (see Claim 2) |

### What you can and can't defend in an interview now

You can now defend:
- **Tests and CI:** 81 tests, run against mocked AWS (moto) with Spotify stubbed. CI runs flake8 and pytest on Python 3.11 (dev pins) and 3.14 (the Lambda layer's verified library versions), and passed on GitHub on pull requests #2–#4 (observed on the PR pages; no logs saved).
- **Error handling:** both handlers log and re-raise, so failures aren't reported as successes.
- **Scoped IAM:** each role's S3 access is limited to the prefixes it uses. Say "scoped to the bucket and prefixes", and add that enforcement was not tested on AWS.
- **Repeatable deploy and teardown** with a fixed bucket name.
- **The date-bug fix:** a regression test that failed before the fix and passes after it.
- **Runtime choice:** moved off `python3.10` (end of support per AWS) to `python3.14`, with layer ARNs taken from the official per-region list rather than guessed.

Still not defensible:
1. **Any AWS number:** Lambda duration or memory, records per run, cost, Athena data scanned, run counts. All NOT MEASURED.
2. **"Ran in production" or "ran daily"**, or "processed N tracks/day". There's no evidence of any AWS run in this repo.
3. **"Glue schema discovery" or "Athena analytics" as things you observed**, unless you did them in the old account and can describe the results.
4. **"Trending data"** as analysis.
5. **"Least-privilege" without qualification.** The policies are scoped, but whether they're sufficient (or minimal) on AWS wasn't tested.
6. **Secrets:** the Spotify secret is no longer on the command line, but it's still a plain Lambda environment variable. Secrets Manager is documented as the better option, not implemented.

### Suggested wording (only what the code supports and was verified locally)

- "Built a serverless ETL pipeline on AWS: an EventBridge-scheduled Python Lambda pulls daily snapshots of a Spotify playlist through the Spotify Web API and stores the raw JSON in Amazon S3."
- "Wrote an S3-triggered Lambda that uses pandas and AWS Data Wrangler (AWS SDK for pandas) to normalise the JSON into album, artist and track Parquet tables, with a Glue crawler and an Athena workgroup set up for SQL queries."
- "Wrote Boto3 deploy and teardown scripts for the whole stack (S3, scoped IAM roles, Lambda on python3.14, EventBridge, Glue, Athena), and covered them with 81 pytest tests against mocked AWS (moto) in a GitHub Actions CI matrix."

Only if you actually did it in the old account, you can add: "ran the crawler and queried the tables in Athena". Avoid production, scale or cost claims.

---

## History: original check at commit `5148787` (2026-11-26)

The text below is the original check, kept unchanged as a dated record (headings moved down one level). Verdicts and caveats in it describe the code at `5148787`; the current verdicts are above.

> **Note:** this report describes the original code at commit `5148787`. Several issues it lists (no tests, the date bug, `AmazonS3FullAccess` on every role, no teardown, no Athena setup, errors returned as 500s, the secret passed on the command line) were addressed later on the `fix/pipeline-hardening` branch. Those fixes are tested with moto only, not on AWS. See "Known limitations" in the README for the current status.

Checked against commit `5148787` on 2026-11-26. "Code supports it" means the code does it. It does not mean there is evidence the code ran: **the repo has no logs, screenshots or outputs from AWS** (see `results/results.md`).

### Claim 1
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

### Claim 2
> "Transformed raw data into Parquet with AWS Data Wrangler, using AWS Glue for schema discovery and Amazon Athena for serverless SQL analytics"

**Verdict: PARTIAL.**

| Part | Status | Evidence |
|---|---|---|
| Raw JSON → Parquet with AWS Data Wrangler | SUPPORTED | `src/transform_lambda/lambda_function.py:93-104` (`wr.s3.to_parquet`, 3 tables, default Snappy codec, confirmed locally in `results/raw/bench_pipeline_50.json`). Runs automatically from an S3 `ObjectCreated` event (`infra/setup_lambda.py:59-96`). |
| Glue for schema discovery | PARTIAL | **It's a Glue crawler**, created by Boto3 (`infra/setup_glue_athena.py:52-74`) and pointed at `s3://<bucket>/transformed_data/`. The code **never starts it** and gives it no schedule; it prints "run the crawler from the AWS Console" (`:76`). Data Wrangler does **not** write to the Glue Catalog: `to_parquet` is called without `dataset=True`, `database=` or `table=`. |
| Athena for SQL analytics | PARTIAL / weak | `athena_client` is created but never used (`infra/setup_glue_athena.py:8`). There's no workgroup, no query-result location and no saved queries. The only Athena artifact is one example query in the README. |

Data-quality issue you should know about: `pd.to_datetime(..., errors='coerce')` on `album_release_date` (`lambda_function.py:86`) **lost 36 of 40 dates** in the local synthetic test, because Spotify mixes `YYYY` and `YYYY-MM-DD` formats (`results/raw/derived_metrics_50.txt`). It was tested only with pandas 3.1.1.

### Claim 3
> "Automated daily processing and infrastructure setup with EventBridge, IAM, and Boto3, enabling repeatable deployment of the full pipeline"

**Verdict: PARTIAL.**

| Part | Status | Evidence |
|---|---|---|
| Daily schedule via EventBridge | SUPPORTED for extraction | `cron(0 12 * * ? *)`, daily at 12:00 UTC, targets `SpotifyExtractData` (`infra/setup_eventbridge.py:7, 56`). The transform is run by an **S3 event, not EventBridge**. The Glue crawler is **not** scheduled. |
| Infrastructure created by code (not the console) | SUPPORTED | Boto3 scripts create the S3 bucket and prefixes (`infra/setup_s3.py`), IAM roles (`infra/setup_iam_roles.py`, `infra/setup_glue_athena.py:25-50`), both Lambdas and the S3 trigger (`infra/setup_lambda.py`), the EventBridge rule (`infra/setup_eventbridge.py`), and the Glue database and crawler. `deploy_all.py` runs them in order. **No Terraform or CloudFormation.** |
| IAM | SUPPORTED, but not least-privilege | Every role gets `AmazonS3FullAccess` (`infra/setup_iam_roles.py:47, 55`; `infra/setup_glue_athena.py:49`). The code's own comment says "Simplified for development, should be scoped down in prod". |
| "Repeatable deployment" | PARTIAL | Most steps handle "already exists", but: (a) `deploy_all.py:15` picks a **random bucket name on every run**, so a rerun creates a new bucket and leaves the old one behind; (b) there's no teardown script and no state tracking, unlike Terraform or CloudFormation; (c) the region fallback is inconsistent (`setup_s3.py:49` defaults to `us-east-1`, `setup_lambda.py:125` to `ap-south-1`; `deploy_all.py` avoids this by setting the region); (d) the Lambda layer ARN is pinned to version 14 (`setup_lambda.py:126`); (e) updating an existing Lambda doesn't update its role or layers (`setup_lambda.py:42-57`). |
| "Full pipeline" | PARTIAL | Starting the crawler and setting up Athena are manual steps (see Claim 2) |

### Things you could not defend in an interview as currently written

1. **Any number** about records, run counts, latency, data volume or cost. None was measured on AWS and no evidence is saved.
2. **"Least-privilege" or "granular" IAM**, which the current README states. The code attaches `AmazonS3FullAccess` everywhere.
3. **"Glue for schema discovery"** unless you actually ran the crawler from the console and can describe the tables it produced.
4. **"Trending data"** as if it were analysis. It's a playlist snapshot.
5. **Error handling.** Both handlers catch every exception and **return** a 500 instead of raising it (`extract …:77-82`, `transform …:120-125`). Lambda then records the invocation as successful, so failures don't trigger retries or error metrics.
6. **Secrets handling.** The Spotify client secret is passed as a command-line argument (`deploy_all.py:29`) and stored as a plain-text Lambda environment variable (`infra/setup_lambda.py:116-120`). `deploy_all.py` also expects long-lived AWS access keys in `credentials.json`. No secret was committed (`results/raw/secret_scan.txt`), but expect the question "why not Secrets Manager or SSM?"

### Suggested wording (only what the code supports)

- "Built a serverless ETL pipeline on AWS: an EventBridge-scheduled Python Lambda pulls daily snapshots of Spotify's Top 50 Global playlist through the Spotify Web API and stores the raw JSON in Amazon S3."
- "Wrote an S3-event-triggered Lambda that uses pandas and AWS Data Wrangler (AWS SDK for pandas) to normalise the JSON into album, artist and track tables stored as Snappy-compressed Parquet. Set up a Glue crawler and Data Catalog database so the tables can be queried in Amazon Athena."
- "Wrote Boto3 deployment scripts that create the S3 bucket, IAM roles, Lambda functions, S3 trigger, EventBridge schedule and Glue crawler from one command."

Only if you actually did it, you can add: "ran the Glue crawler and queried the tables in Athena". Avoid "least-privilege", "repeatable infrastructure as code" and any metric until you have evidence.
