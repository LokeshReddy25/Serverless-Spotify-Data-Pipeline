"""IAM role setup, run against moto.

moto records IAM roles and policies but does not enforce them, so these tests check which
policies are created and attached. They cannot prove the permissions are sufficient on AWS.
"""
import json

import boto3
import pytest

from infra import setup_iam_roles as iam_setup

BUCKET = "my-pipeline-bucket"


@pytest.fixture
def iam(aws):
    return boto3.client("iam")


def _inline(iam, role):
    doc = iam.get_role_policy(RoleName=role, PolicyName=iam_setup.INLINE_POLICY_NAME)["PolicyDocument"]
    return doc if isinstance(doc, dict) else json.loads(doc)


def _attached(iam, role):
    return sorted(p["PolicyArn"] for p in iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"])


def _grants(policy):
    """Flatten a policy into {(action, resource)} pairs."""
    pairs = set()
    for stmt in policy["Statement"]:
        assert stmt["Effect"] == "Allow"
        for action in stmt["Action"]:
            for resource in stmt["Resource"]:
                pairs.add((action, resource))
    return pairs


def test_roles_are_created_without_s3_full_access(iam):
    iam_setup.setup_roles(iam, BUCKET)

    assert _attached(iam, iam_setup.EXTRACT_ROLE) == [iam_setup.LAMBDA_BASIC_EXECUTION]
    assert _attached(iam, iam_setup.TRANSFORM_ROLE) == [iam_setup.LAMBDA_BASIC_EXECUTION]
    assert _attached(iam, iam_setup.GLUE_ROLE) == [iam_setup.GLUE_SERVICE_ROLE]


def test_extract_role_can_only_write_raw_json(iam):
    iam_setup.setup_roles(iam, BUCKET)
    assert _grants(_inline(iam, iam_setup.EXTRACT_ROLE)) == {
        ("s3:PutObject", f"arn:aws:s3:::{BUCKET}/raw_data/to_process/*"),
    }


def test_transform_role_has_only_the_actions_it_calls(iam):
    iam_setup.setup_roles(iam, BUCKET)
    assert _grants(_inline(iam, iam_setup.TRANSFORM_ROLE)) == {
        ("s3:GetObject", f"arn:aws:s3:::{BUCKET}/raw_data/to_process/*"),
        ("s3:DeleteObject", f"arn:aws:s3:::{BUCKET}/raw_data/to_process/*"),
        ("s3:PutObject", f"arn:aws:s3:::{BUCKET}/raw_data/processed/*"),
        ("s3:PutObject", f"arn:aws:s3:::{BUCKET}/transformed_data/*"),
    }


def test_glue_role_can_only_list_and_read_transformed_data(iam):
    iam_setup.setup_roles(iam, BUCKET)
    policy = _inline(iam, iam_setup.GLUE_ROLE)
    assert _grants(policy) == {
        ("s3:ListBucket", f"arn:aws:s3:::{BUCKET}"),
        ("s3:GetObject", f"arn:aws:s3:::{BUCKET}/transformed_data/*"),
    }
    list_stmt = next(s for s in policy["Statement"] if s["Action"] == ["s3:ListBucket"])
    assert list_stmt["Condition"] == {"StringLike": {"s3:prefix": ["transformed_data", "transformed_data/*"]}}


@pytest.mark.parametrize("make_policy", [iam_setup.extract_s3_policy, iam_setup.transform_s3_policy,
                                         iam_setup.glue_s3_policy])
def test_no_wildcard_actions_or_resources_outside_the_bucket(make_policy):
    for action, resource in _grants(make_policy(BUCKET)):
        assert "*" not in action
        assert resource.startswith(f"arn:aws:s3:::{BUCKET}")
        assert resource != "*"


def test_trust_policies_name_the_right_service(iam):
    iam_setup.setup_roles(iam, BUCKET)

    def principal(role):
        doc = iam.get_role(RoleName=role)["Role"]["AssumeRolePolicyDocument"]
        doc = doc if isinstance(doc, dict) else json.loads(doc)
        return doc["Statement"][0]["Principal"]["Service"]

    assert principal(iam_setup.EXTRACT_ROLE) == "lambda.amazonaws.com"
    assert principal(iam_setup.TRANSFORM_ROLE) == "lambda.amazonaws.com"
    assert principal(iam_setup.GLUE_ROLE) == "glue.amazonaws.com"


def test_rerun_detaches_s3_full_access_from_older_deployments(iam):
    # Simulate a role created by the previous version of this script.
    iam.create_role(RoleName=iam_setup.TRANSFORM_ROLE,
                    AssumeRolePolicyDocument=json.dumps(iam_setup._trust_policy("lambda.amazonaws.com")))
    iam.attach_role_policy(RoleName=iam_setup.TRANSFORM_ROLE, PolicyArn=iam_setup.S3_FULL_ACCESS)

    iam_setup.setup_roles(iam, BUCKET)
    iam_setup.setup_roles(iam, BUCKET)  # idempotent

    assert iam_setup.S3_FULL_ACCESS not in _attached(iam, iam_setup.TRANSFORM_ROLE)
    assert _grants(_inline(iam, iam_setup.TRANSFORM_ROLE))
