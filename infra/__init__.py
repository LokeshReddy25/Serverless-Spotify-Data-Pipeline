"""Boto3 scripts that create (and tear down) the pipeline's AWS resources.

Run them from the repository root as modules, e.g. `python -m infra.setup_s3 --bucket-name NAME`,
or run everything with `python deploy_all.py`. Remove everything with `python -m infra.teardown`.
"""
