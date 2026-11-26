# Results Summary

> **Note:** this report describes the original code at commit `5148787`. Several issues it lists (no tests, the date bug, `AmazonS3FullAccess` on every role, no teardown, no Athena setup, errors returned as 500s, the secret passed on the command line) were addressed later on the `fix/pipeline-hardening` branch. Those fixes are tested with moto only, not on AWS. See "Known limitations" in the README for the current status.

Date: 2026-11-26 · Branch: `docs/measured-results` · Machine: i5-12500H (12C/16T), 15.71 GiB RAM, Windows 11 Home 10.0.26300.
Details: [results/results.md](results/results.md) · Claims check: [results/resume_claims_check.md](results/resume_claims_check.md) · Raw logs: `results/raw/`

## Verified numbers (all local; S3 mocked with moto; synthetic input, not real Spotify data)

| Metric | Value | Raw log |
|---|---|---|
| Unit tests | 0 (none exist) | `results/raw/environment.txt` |
| py_compile | 9/9 files OK | `results/raw/static_checks.txt` |
| pyflakes (ad hoc) | 5 warnings, 0 errors | `results/raw/static_checks.txt` |
| Raw JSON written by extract handler (50 synthetic items) | 28102 bytes | `results/raw/bench_pipeline_50.json` |
| Parquet written by transform handler | 20043 bytes total (albums 6228, artists 4619, tracks 9196), SNAPPY | `results/raw/bench_pipeline_50.json` |
| JSON ÷ Parquet bytes | 1.402 (synthetic; not like-for-like) | `results/raw/derived_metrics_50.txt` |
| Rows out | albums 40, artists 35, tracks 50 | `results/raw/bench_pipeline_50.json` |
| Extract handler, local (Spotify stubbed) | median 26.6 ms, min 22.2, max 28.3 (n=5) | `results/raw/timing_table.txt` |
| Transform handler, local | median 341.7 ms, min 290.9, max 418.3 (n=5) | `results/raw/timing_table.txt` |
| Transform import (pandas + awswrangler), fresh process | median 3214.5 ms, min 3154.1, max 10924.6 (n=5) | `results/raw/timing_table.txt` |
| Release-date bug | 36 of 40 album dates became null (mixed `YYYY` / `YYYY-MM-DD`) | `results/raw/derived_metrics_50.txt` |
| Secrets in code or history | 0 hits (scanner confirmed against planted fakes) | `results/raw/secret_scan.txt` |

## Resume claims

| Claim | Verdict |
|---|---|
| 1. Lambda extracts "trending" Spotify data → raw JSON in S3 | **SUPPORTED** in code. "Trending" overstates it: it's a daily snapshot of one playlist. Spotify's Nov 2024 API restriction may block the default playlist. |
| 2. Parquet via Data Wrangler; Glue schema discovery; Athena SQL | **PARTIAL.** Parquet: supported. Glue: a crawler is created but never started by code. Athena: no resources, only a README query. |
| 3. Daily automation + Boto3 infrastructure setup, repeatable deployment | **PARTIAL.** Daily EventBridge rule (extract only) and Boto3-created infrastructure are supported. Repeatability is limited (random bucket name per run, no teardown, no IaC state). IAM is not least-privilege. |

## NOT MEASURED (no saved evidence; the AWS account is gone)
Lambda duration and memory on AWS · Lambda cold start on AWS · Athena runtime and data scanned · real S3 object sizes · records per real run · completed scheduled runs · Glue crawler results · cost · test pass rate and coverage (no tests) · whether Spotify still serves the default playlist to your app.

## What was added or changed
- `benchmarks/`: `make_sample.py` (synthetic input), `bench_pipeline.py` (runs the unmodified handlers against moto), `derive_metrics.py`, `secret_scan.sh`, `requirements.txt` (pinned versions), and `sample_data/synthetic_playlist_50.json`
- `results/`: `results.md`, `resume_claims_check.md`, `raw/*` (command plus raw output for every measurement)
- `README.md`: rewritten with a Mermaid diagram matching the actual wiring, setup, IAM permissions, a cost note (no figures), a Results section labelled as local measurements on a synthetic 50-track sample with S3 mocked (with NOT MEASURED), and a Known limitations section. Removed the unsupported "least-privilege", "granular" and "deployed entirely on AWS" wording. Copyright section kept as it was.
- `.gitignore`: added `.env.*`, `*.pem`, `*.key` (it already covered `.env`, `credentials.json`, `.aws/`, `.venv`, `*.zip`)
- **Pipeline code (`src/`, `infra/`, `deploy_all.py`): unchanged.**

## Still to do by hand
1. Decide whether you really ran the Glue crawler and Athena queries in the old account. Only claim them if you did and can describe the result.
2. Confirm whether real Spotify data ever flowed, or only mock data (`.gitignore` mentions `push_mock_data.py`). Word the resume to match.
3. If you want AWS numbers, redeploy in a new account and save CloudWatch REPORT lines, the Athena "data scanned" figure and billing to `results/`.
4. Optional code fixes (not done, since the brief was not to change pipeline code): date parsing (`format='mixed'` or keeping the raw string), raising exceptions instead of returning 500, scoped S3 IAM policy, Secrets Manager for the Spotify secret, a fixed bucket name and a teardown script, and a few unit tests.
5. Update your resume using the suggested wording in `results/resume_claims_check.md`.
