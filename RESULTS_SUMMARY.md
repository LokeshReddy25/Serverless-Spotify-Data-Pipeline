# Results Summary

## Current status: refreshed 2026-11-26 against `main` at `d6afb68`

Details: [results/results.md](results/results.md) · Claims check: [results/resume_claims_check.md](results/resume_claims_check.md) · Raw logs: `results/raw/`

**Nothing has been deployed to AWS.** All verification is local: tests against moto (an in-memory AWS mock), with the Spotify API stubbed, plus checks against official AWS and AWS SDK for pandas documentation.

### Verified numbers (local, re-run for this refresh)

| Metric | Value | Raw log |
|---|---|---|
| Tests, Python 3.11.9 (`requirements-dev.txt`) | 81 passed, 0 failed; 91% coverage (statements + branches); flake8 clean | `results/raw/claims_refresh_tests_py311-dev.txt` |
| Tests, Python 3.14.10 + layer versions, pandas 3.0.6 | 81 passed, 0 failed; 91% coverage; flake8 clean | `results/raw/claims_refresh_tests_py314-pandas3.0.6.txt` |
| Tests, Python 3.14.10 + layer versions, pandas 3.1.1 | 81 passed, 0 failed; 91% coverage; flake8 clean | `results/raw/claims_refresh_tests_py314-pandas3.1.1.txt` |
| Date-bug regression tests | Failed on the original code, pass after the fix and in every environment above | `results/raw/date_bug_{before,after}_fix.txt` |
| CI on GitHub | Passed on PR #2 (2 checks), #3 (6 checks), #4 (6 checks), as observed on the PR pages on 2026-11-26. **No logs saved.** | — |

### Resume claims

| Claim | At `5148787` | Now |
|---|---|---|
| 1. Lambda extracts Spotify data → raw JSON in S3 | SUPPORTED (code only) | **SUPPORTED** (verified locally). "Trending" still overstates it. |
| 2. Parquet via Data Wrangler; Glue schema discovery; Athena SQL | PARTIAL | **PARTIAL.** Parquet: supported. Glue crawler and Athena workgroup are now set up by code and verified in moto, but no crawl or query has ever run. |
| 3. Daily automation + Boto3/IAM infrastructure, repeatable deployment | PARTIAL | **SUPPORTED in code (verified in moto only; never deployed to AWS).** Fixed bucket name, redeploy in place, teardown, scoped IAM. IAM sufficiency untested. "Full pipeline" includes the Glue crawler and Athena steps, which have never run: no crawl has produced tables and no Athena query has been executed (see Claim 2). |

### What was merged since the first measurement

- **Fixed:** date-bug fix with regression tests; handlers raise instead of returning 500.
- **Security:** Spotify secret no longer on the command line, and no `credentials.json`; bucket- and prefix-scoped IAM instead of `AmazonS3FullAccess`.
- **Deployment:** fixed bucket name and a teardown script; Athena workgroup with a scan limit; one-command crawler step.
- **Testing:** 81 pytest tests against moto; GitHub Actions CI with a Python 3.11 + 3.14 matrix.
- **Runtime:** moved from `python3.10` (end of support per AWS) to `python3.14` with documented per-region `AWSSDKPandas-Python314` layer ARNs (release 3.18.0), overridable and validated.

### NOT MEASURED (nothing deployed)

Lambda duration, memory and cold start on AWS · whether the layer ARNs resolve in each region · the layer's actual pandas/numpy versions · IAM sufficiency · S3 → Lambda and EventBridge invocations on AWS · Glue crawler output · Athena runtime and data scanned · records per real run · completed scheduled runs · real S3 object sizes · cost · Spotify API access with real credentials.

### Still to do by hand

1. Decide whether you ran the Glue crawler and Athena queries in the old account. Only claim them if you did.
2. Confirm whether real Spotify data ever flowed. Your Spotify app may also be unable to read the default editorial playlist.
3. To get AWS numbers, deploy to a non-production account (`python deploy_all.py`), run it, save CloudWatch `REPORT` lines, the crawler output, an Athena query's "data scanned" figure and billing to `results/`, then run `python -m infra.teardown --yes`.
4. Still open in code: Spotify secret in Secrets Manager; transform Lambda memory size; crawler schedule.
5. Update your resume using the suggested wording in `results/resume_claims_check.md`.

---

## History: original summary at commit `5148787` (2026-11-26)

The text below is the original summary, kept unchanged as a dated record. Several issues it lists were fixed later (see above).

> **Note:** this report describes the original code at commit `5148787`. Several issues it lists (no tests, the date bug, `AmazonS3FullAccess` on every role, no teardown, no Athena setup, errors returned as 500s, the secret passed on the command line) were addressed later on the `fix/pipeline-hardening` branch. Those fixes are tested with moto only, not on AWS. See "Known limitations" in the README for the current status.

Date: 2026-11-26 · Branch: `docs/measured-results` · Machine: i5-12500H (12C/16T), 15.71 GiB RAM, Windows 11 Home 10.0.26300.
Details: [results/results.md](results/results.md) · Claims check: [results/resume_claims_check.md](results/resume_claims_check.md) · Raw logs: `results/raw/`

### Verified numbers (all local; S3 mocked with moto; synthetic input, not real Spotify data)

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

### Resume claims

| Claim | Verdict |
|---|---|
| 1. Lambda extracts "trending" Spotify data → raw JSON in S3 | **SUPPORTED** in code. "Trending" overstates it: it's a daily snapshot of one playlist. Spotify's Nov 2024 API restriction may block the default playlist. |
| 2. Parquet via Data Wrangler; Glue schema discovery; Athena SQL | **PARTIAL.** Parquet: supported. Glue: a crawler is created but never started by code. Athena: no resources, only a README query. |
| 3. Daily automation + Boto3 infrastructure setup, repeatable deployment | **PARTIAL.** Daily EventBridge rule (extract only) and Boto3-created infrastructure are supported. Repeatability is limited (random bucket name per run, no teardown, no IaC state). IAM is not least-privilege. |

### NOT MEASURED (no saved evidence; the AWS account is gone)
Lambda duration and memory on AWS · Lambda cold start on AWS · Athena runtime and data scanned · real S3 object sizes · records per real run · completed scheduled runs · Glue crawler results · cost · test pass rate and coverage (no tests) · whether Spotify still serves the default playlist to your app.

### What was added or changed
- `benchmarks/`: `make_sample.py` (synthetic input), `bench_pipeline.py` (runs the unmodified handlers against moto), `derive_metrics.py`, `secret_scan.sh`, `requirements.txt` (pinned versions), and `sample_data/synthetic_playlist_50.json`
- `results/`: `results.md`, `resume_claims_check.md`, `raw/*` (command plus raw output for every measurement)
- `README.md`: rewritten with a Mermaid diagram matching the actual wiring, setup, IAM permissions, a cost note (no figures), a Results section labelled as local measurements on a synthetic 50-track sample with S3 mocked (with NOT MEASURED), and a Known limitations section. Removed the unsupported "least-privilege", "granular" and "deployed entirely on AWS" wording. Copyright section kept as it was.
- `.gitignore`: added `.env.*`, `*.pem`, `*.key` (it already covered `.env`, `credentials.json`, `.aws/`, `.venv`, `*.zip`)
- **Pipeline code (`src/`, `infra/`, `deploy_all.py`): unchanged.**

### Still to do by hand
1. Decide whether you really ran the Glue crawler and Athena queries in the old account. Only claim them if you did and can describe the result.
2. Confirm whether real Spotify data ever flowed, or only mock data (`.gitignore` mentions `push_mock_data.py`). Word the resume to match.
3. If you want AWS numbers, redeploy in a new account and save CloudWatch REPORT lines, the Athena "data scanned" figure and billing to `results/`.
4. Optional code fixes (not done, since the brief was not to change pipeline code): date parsing (`format='mixed'` or keeping the raw string), raising exceptions instead of returning 500, scoped S3 IAM policy, Secrets Manager for the Spotify secret, a fixed bucket name and a teardown script, and a few unit tests.
5. Update your resume using the suggested wording in `results/resume_claims_check.md`.
