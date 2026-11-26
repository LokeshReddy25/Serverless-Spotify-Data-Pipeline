"""LOCAL benchmark of the unmodified extract + transform Lambda handlers.

Nothing here touches AWS or Spotify:
  * S3 is replaced by moto's in-memory mock (mock_aws). The AWS_* env vars set below are
    the fake placeholder values moto documents ("testing"); they exist only inside this
    process and are never written to disk. ~/.aws is never read (AWS_SHARED_CREDENTIALS_FILE
    and AWS_CONFIG_FILE point to a non-existent path).
  * The extract handler's two Spotify HTTP helpers (get_spotify_token, extract_playlist_data)
    are monkeypatched to return the synthetic sample file. The handler code itself is not edited.

Each trial runs in a fresh subprocess so imports (pandas/awswrangler) are cold every time.
Timings are LOCAL wall-clock on this laptop -- NOT AWS Lambda durations.

Usage: python benchmarks/bench_pipeline.py <sample.json> <trials> <out.json>
"""
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BUCKET = "local-benchmark-bucket"


def _isolate_env():
    os.environ.update({
        "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_SHARED_CREDENTIALS_FILE": str(REPO / "__no_such_file__"),
        "AWS_CONFIG_FILE": str(REPO / "__no_such_file__"),
    })


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def one_trial(sample_path):
    _isolate_env()
    from moto import mock_aws
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    res = {}
    with mock_aws():
        import boto3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET)

        # ---- extract handler (Spotify HTTP stubbed) ----
        t0 = time.perf_counter()
        ext = _load("extract_lambda_function", REPO / "src/extract_lambda/lambda_function.py")
        res["extract_import_s"] = time.perf_counter() - t0
        ext.get_spotify_token = lambda cid, secret: "stub-token"
        ext.extract_playlist_data = lambda token, pid: sample
        os.environ.update({"SPOTIFY_CLIENT_ID": "stub", "SPOTIFY_CLIENT_SECRET": "stub",
                           "S3_BUCKET_NAME": BUCKET})
        t0 = time.perf_counter()
        out = ext.lambda_handler({}, None)
        res["extract_handler_s"] = time.perf_counter() - t0
        if out["statusCode"] != 200:
            raise SystemExit(f"extract handler failed: {out}")
        raw_key = json.loads(out["body"])["s3_path"]
        res["raw_json_bytes_in_s3"] = s3.head_object(Bucket=BUCKET, Key=raw_key)["ContentLength"]

        # ---- transform handler (real awswrangler -> moto S3) ----
        t0 = time.perf_counter()
        tr = _load("transform_lambda_function", REPO / "src/transform_lambda/lambda_function.py")
        res["transform_import_s"] = time.perf_counter() - t0
        os.environ["TRANSFORMED_S3_BUCKET"] = BUCKET
        event = {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": raw_key}}}]}
        t0 = time.perf_counter()
        out = tr.lambda_handler(event, None)
        res["transform_handler_s"] = time.perf_counter() - t0
        if out["statusCode"] != 200:
            raise SystemExit(f"transform handler failed: {out}")

        import awswrangler as wr
        objs = s3.list_objects_v2(Bucket=BUCKET, Prefix="transformed_data/")["Contents"]
        res["parquet_objects"] = {}
        for o in objs:
            df = wr.s3.read_parquet(f"s3://{BUCKET}/{o['Key']}")
            table = o["Key"].split("/")[1]
            res["parquet_objects"][table] = {"key": o["Key"], "bytes": o["Size"], "rows": len(df),
                                             "columns": list(df.columns),
                                             "dtypes": {c: str(t) for c, t in df.dtypes.items()}}
        import pyarrow.parquet as pq, io
        body = s3.get_object(Bucket=BUCKET, Key=objs[0]["Key"])["Body"].read()
        md = pq.ParquetFile(io.BytesIO(body)).metadata
        res["parquet_compression_codec"] = md.row_group(0).column(0).compression
        keys = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix="raw_data/")["Contents"]]
        res["raw_keys_after_transform"] = keys
    return res


def summarise(vals):
    return {"median": statistics.median(vals), "min": min(vals), "max": max(vals), "n": len(vals),
            "values": vals}


def main():
    sample, trials, out_path = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
    runs = []
    for i in range(trials):
        p = subprocess.run([sys.executable, __file__, "--trial", sample],
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(p.stdout, p.stderr)
            raise SystemExit(f"trial {i + 1} FAILED (exit {p.returncode})")
        runs.append(json.loads(p.stdout.strip().splitlines()[-1]))
        print(f"trial {i + 1}/{trials} ok")
    timing_keys = ["extract_import_s", "extract_handler_s", "transform_import_s", "transform_handler_s"]
    report = {
        "sample_file": sample,
        "timings_seconds": {k: summarise([r[k] for r in runs]) for k in timing_keys},
        "raw_json_bytes_in_s3": sorted({r["raw_json_bytes_in_s3"] for r in runs}),
        "parquet_bytes_per_table": {t: sorted({r["parquet_objects"][t]["bytes"] for r in runs})
                                    for t in runs[0]["parquet_objects"]},
        "first_trial_detail": runs[0],
    }
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--trial":
        print(json.dumps(one_trial(sys.argv[2])))
    else:
        main()
