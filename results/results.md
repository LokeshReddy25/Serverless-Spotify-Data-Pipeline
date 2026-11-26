# Measured Results — Serverless Spotify Data Pipeline

> **Note:** this report describes the original code at commit `5148787`. Several issues it lists (no tests, the date bug, `AmazonS3FullAccess` on every role, no teardown, no Athena setup, errors returned as 500s, the secret passed on the command line) were addressed later on the `fix/pipeline-hardening` branch. Those fixes are tested with moto only, not on AWS. See "Known limitations" in the README for the current status.

**Date measured:** 2026-11-26 (local time, UTC+05:30). Source: `results/raw/environment.txt`.
**Branch:** `docs/measured-results`, base commit `5148787`.

## Machine

| Item | Value | Source |
|---|---|---|
| CPU | 12th Gen Intel(R) Core(TM) i5-12500H, 12 cores / 16 logical processors | `results/raw/environment.txt` |
| RAM | 16869548032 bytes (15.71 GiB) | `results/raw/environment.txt` |
| OS | Microsoft Windows 11 Home 10.0.26300, 64-bit | `results/raw/environment.txt` |
| Python (benchmarks) | 3.11.9 (the Lambdas are configured for `python3.10`) | `results/raw/environment.txt` |
| Key libraries | awswrangler 3.18.0, pandas 3.1.1, pyarrow 26.0.1, boto3 1.44.12, moto 5.2.6 | `benchmarks/requirements.txt` |

## Important limits on everything below

- **No AWS was used.** The AWS CLI has no credentials and the original account is gone. S3 was replaced by **moto**, a local in-memory mock. moto needs placeholder values (`testing`) in its own process environment. These are fake, were never written to disk, and `~/.aws` was never read.
- **No Spotify API calls were made.** The repository contains **no** saved Spotify responses, so the input is a **synthetic** file generated from the fields the transform code reads: `benchmarks/sample_data/synthetic_playlist_50.json` (50 items, sha256 `19a49ff8…6596610`, made by `benchmarks/make_sample.py`, seed 42). Real Spotify responses contain many more fields, so **the sizes below are not representative of real data.**
- The local library versions are newer than those in the Lambda layer the code pins (`AWSSDKPandas-Python310:14`), and that layer's versions were not checked.
- All timings are **local wall-clock time on this laptop, not AWS Lambda durations**.

## Measured metrics

| Metric | Value | How measured | Raw log |
|---|---|---|---|
| Unit tests | **None exist.** No test files and no pytest, tox or pyproject config | `ls tests test* pytest.ini setup.cfg tox.ini pyproject.toml …` | `results/raw/environment.txt` |
| Syntax check (all 9 `.py` files) | 9/9 compile | `python -m py_compile deploy_all.py infra/*.py src/*/lambda_function.py` | `results/raw/static_checks.txt` |
| pyflakes (not configured in repo; run ad hoc) | 5 warnings, 0 errors: 4× f-string without placeholders, 1× unused variable `get_token_start` | `python -m pyflakes deploy_all.py infra src` | `results/raw/static_checks.txt` |
| Raw JSON size written by the extract handler (synthetic, 50 items) | 28102 bytes | Real handler, Spotify calls stubbed, `head_object` on moto S3 | `results/raw/bench_pipeline_50.json` |
| Parquet size after the real transform handler (awswrangler `wr.s3.to_parquet`, code defaults) | albums 6228 B, artists 4619 B, tracks 9196 B, total 20043 B | `python benchmarks/bench_pipeline.py benchmarks/sample_data/synthetic_playlist_50.json 5 results/raw/bench_pipeline_50.json` (same in all 5 trials) | `results/raw/bench_pipeline_50.json` |
| Parquet codec | SNAPPY (awswrangler default; the code sets none) | pyarrow metadata of the written file | `results/raw/bench_pipeline_50.json` |
| Raw JSON ÷ total Parquet bytes (synthetic) | 1.402 (Parquet total is 0.713× the JSON) | `python benchmarks/derive_metrics.py …` | `results/raw/derived_metrics_50.txt` |
| Rows written (synthetic input) | albums 40, artists 35, tracks 50 | Read back with `wr.s3.read_parquet` | `results/raw/bench_pipeline_50.json` |
| Extract handler execution, local (Spotify stubbed, moto S3) | median 26.6 ms, min 22.2 ms, max 28.3 ms (n=5) | `bench_pipeline.py`, `time.perf_counter` around `lambda_handler` | `results/raw/bench_pipeline_50.json`, `results/raw/timing_table.txt` |
| Transform handler execution, local (moto S3) | median 341.7 ms, min 290.9 ms, max 418.3 ms (n=5) | same | same |
| Transform module import (pandas + awswrangler), fresh process | median 3214.5 ms, min 3154.1 ms, max 10924.6 ms (n=5; the max is trial 1, first cold load from disk) | same | same |
| Album release dates lost by `pd.to_datetime(..., errors='coerce')` (`src/transform_lambda/lambda_function.py:86`) | 36 of 40 became null in this sample | The first value in the column was year-only (`"YYYY"`, a format Spotify uses for some albums). pandas inferred that format and turned every full date into null. `benchmarks/derive_metrics.py` | `results/raw/derived_metrics_50.txt` |
| Secrets in code or git history | 0 pattern hits across 2 commits and the working tree. The scanner was confirmed to catch planted fakes. | `bash benchmarks/secret_scan.sh` | `results/raw/secret_scan.txt`, `results/raw/secret_scan_positive_control.txt`. A rescan after adding these files has 1 false positive: the placeholder `"stub-token"` in `benchmarks/bench_pipeline.py:59` (`results/raw/secret_scan_final.txt`). |

The compression figure is **not** like-for-like. The transform writes only 15 output columns (5 + 3 + 7) and splits them into 3 tables, so the ratio mixes field selection with Parquet encoding. It also comes from synthetic data.

## NOT MEASURED

| Metric | Why |
|---|---|
| Records per real run | No saved log, raw JSON or Parquet from a real run exists in the repo or its git history |
| Lambda duration and memory used per invocation | Needs CloudWatch logs or REPORT lines. None are saved and the account is gone. |
| Lambda cold start on AWS | Same as above. The local import time is not a substitute. |
| Athena query runtime and data scanned | No Athena result files or screenshots are saved. The code never runs a query (`athena_client` in `infra/setup_glue_athena.py:8` is never used). |
| S3 object sizes of real data | No S3 inventory or listing was saved |
| Cost per run or per month | No billing export or screenshot is saved |
| Number of completed scheduled runs | No EventBridge or CloudWatch evidence is saved |
| Glue crawler results (tables, schema, run time) | No saved output. The code creates the crawler but never starts it (`infra/setup_glue_athena.py:76` says to run it from the console). |
| Unit test pass rate and coverage | No tests exist |
| Whether Spotify still serves the default playlist (`37i9dQZEVXbMDoHDwVN2tF`) to this app's credentials | Can't be tested without Spotify credentials, which were not used by design |

## Saved evidence from earlier AWS runs

**None found.** The repo has 11 tracked files across 2 commits: code, README, `.gitignore` and a requirements file. There are no logs, screenshots, sample JSON/Parquet, Athena results, CloudWatch exports or cost screenshots, either now or in history (`results/raw/secret_scan.txt` lists every file ever committed; `results/raw/environment.txt` shows the evidence-file search).

## What the pipeline actually does

The pipeline has two Python Lambda functions. A Boto3 script creates an EventBridge rule that runs the extract Lambda once a day at 12:00 UTC. The extract Lambda gets a Spotify client-credentials token, fetches the first page of tracks from one playlist (the Top 50 Global playlist by default), and writes the response unchanged as a JSON file to `raw_data/to_process/` in S3. That upload fires an S3 event notification, which runs the transform Lambda. The transform Lambda uses pandas to split the tracks into album, artist and track tables, drops duplicates, writes each table as a Snappy-compressed Parquet file under `transformed_data/` with awswrangler, and moves the raw file to `raw_data/processed/`. A Boto3 script also creates a Glue database and a Glue crawler pointed at `transformed_data/`, but the crawler has to be started by hand. Nothing in the code creates Athena resources or runs queries. The README has one example query. All infrastructure is created by Boto3 scripts, not by Terraform or CloudFormation. All IAM roles get `AmazonS3FullAccess`. The repo has no tests, no saved run evidence and no measurements from AWS. Locally, on synthetic data, both handlers run end to end against a mocked S3.
