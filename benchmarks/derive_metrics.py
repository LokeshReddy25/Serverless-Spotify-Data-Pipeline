"""Derive size ratio and date-null counts from the benchmark output + sample (local, synthetic).

The date check repeats the pd.to_datetime(..., errors="coerce") call the transform Lambda made at
commit 5148787. The transform no longer makes that call (see tests/test_release_dates.py).
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pandas as pd

rep = json.loads(Path(sys.argv[1]).read_text())
raw = rep["raw_json_bytes_in_s3"][0]
pq = {t: v[0] for t, v in rep["parquet_bytes_per_table"].items()}
total = sum(pq.values())
print(f"raw_json_bytes={raw}")
print(f"parquet_bytes={pq} total={total}")
print(f"raw_json_bytes / total_parquet_bytes = {raw/total:.3f}")
print(f"total_parquet_bytes / raw_json_bytes = {total/raw:.3f}")
# Re-run the transform's own album function + the same to_datetime call on the sample
spec = importlib.util.spec_from_file_location("t", "src/transform_lambda/lambda_function.py")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
items = json.loads(Path(sys.argv[2]).read_text())["items"]
alb = m.process_album(items)
src = alb["album_release_date"].copy()
year_only = src.str.fullmatch(r"\d{4}").sum()
conv = pd.to_datetime(alb["album_release_date"], errors="coerce")   # same call as lambda_function.py:86 at 5148787
print(f"pandas={pd.__version__}")
print(f"albums={len(alb)} year_only_release_dates_in_input={year_only} full_date_inputs={len(alb)-year_only}")
print(f"null_release_dates_after_to_datetime={conv.isna().sum()}")
print("first_input_value_format=", "year-only" if src.iloc[0].isdigit() else "full-date")
