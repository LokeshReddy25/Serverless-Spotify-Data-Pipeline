"""Glue crawler step and Athena workgroup, against moto (not real AWS)."""
import boto3
import pytest

from infra import config, run_crawler, setup_glue_athena, setup_iam_roles

BUCKET = "glue-test-bucket"


@pytest.fixture
def athena(aws):
    return boto3.client("athena")


@pytest.fixture
def glue_with_crawler(aws):
    iam, glue = boto3.client("iam"), boto3.client("glue")
    setup_iam_roles.setup_roles(iam, BUCKET)
    setup_glue_athena.setup_glue(glue, iam, BUCKET)
    return glue


def test_workgroup_has_result_location_and_scan_limit(athena):
    setup_glue_athena.setup_athena_workgroup(athena, BUCKET)

    wg = athena.get_work_group(WorkGroup=config.ATHENA_WORKGROUP)["WorkGroup"]
    cfg = wg["Configuration"]
    assert cfg["ResultConfiguration"]["OutputLocation"] == f"s3://{BUCKET}/athena_results/"
    assert cfg["EnforceWorkGroupConfiguration"] is True
    assert cfg["BytesScannedCutoffPerQuery"] == 1024 ** 3


class _AthenaRecordingUpdates:
    """moto has not implemented athena.update_work_group; record the call instead of sending it."""

    def __init__(self, athena):
        self._athena, self.updates = athena, []

    def __getattr__(self, name):
        return getattr(self._athena, name)

    def update_work_group(self, **kwargs):
        self.updates.append(kwargs)


def test_existing_workgroup_is_updated_not_duplicated(athena):
    setup_glue_athena.setup_athena_workgroup(athena, BUCKET)
    recorder = _AthenaRecordingUpdates(athena)
    setup_glue_athena.setup_athena_workgroup(recorder, "other-bucket")

    names = [w["Name"] for w in athena.list_work_groups()["WorkGroups"]]
    assert names.count(config.ATHENA_WORKGROUP) == 1
    assert recorder.updates == [{"WorkGroup": config.ATHENA_WORKGROUP, "ConfigurationUpdates": {
        "ResultConfigurationUpdates": {"OutputLocation": "s3://other-bucket/athena_results/"},
        "EnforceWorkGroupConfiguration": True,
        "BytesScannedCutoffPerQuery": 1024 ** 3,
    }}]


def test_deploy_all_run_crawler_flag_starts_the_crawler(aws, monkeypatch):
    import deploy_all
    from infra import setup_lambda
    started = []
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "value")
    # Skip the Lambda step (covered in test_deployment.py); this test is about the crawler flag.
    monkeypatch.setattr(setup_lambda, "deploy_lambdas", lambda *a, **k: None)
    monkeypatch.setattr(deploy_all.setup_eventbridge, "setup_schedule", lambda *a, **k: None)
    monkeypatch.setattr(run_crawler, "start_crawler", lambda glue: started.append(True))

    deploy_all.main(["--bucket-name", BUCKET, "--run-crawler"])
    assert started == [True]


def test_run_crawler_starts_the_crawler(glue_with_crawler, capsys):
    assert run_crawler.start_crawler(glue_with_crawler) is True
    assert glue_with_crawler.get_crawler(Name=config.GLUE_CRAWLER)["Crawler"]["State"] == "RUNNING"


def test_run_crawler_reports_already_running(glue_with_crawler, capsys):
    run_crawler.start_crawler(glue_with_crawler)
    assert run_crawler.start_crawler(glue_with_crawler) is False
    assert "already running" in capsys.readouterr().out


class FakeGlue:
    """Crawler that reports RUNNING, STOPPING, then READY with a finished crawl."""

    def __init__(self, states, last_crawl):
        self.states, self.last_crawl = list(states), last_crawl

    def get_crawler(self, Name):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"Crawler": {"Name": Name, "State": state, "LastCrawl": self.last_crawl}}

    def get_tables(self, DatabaseName):
        return {"TableList": [{"Name": "albums"}, {"Name": "artists"}, {"Name": "tracks"}]}


def test_wait_for_crawler_returns_status_and_lists_tables(capsys):
    glue = FakeGlue(["RUNNING", "STOPPING", "READY"], {"Status": "SUCCEEDED"})
    assert run_crawler.wait_for_crawler(glue, timeout_s=5, poll_interval_s=0) == "SUCCEEDED"
    out = capsys.readouterr().out
    assert "albums, artists, tracks" in out


def test_wait_for_crawler_times_out():
    glue = FakeGlue(["RUNNING"], {})
    with pytest.raises(SystemExit, match="still RUNNING"):
        run_crawler.wait_for_crawler(glue, timeout_s=0, poll_interval_s=0)


def test_run_crawler_cli_fails_when_crawl_does_not_succeed(monkeypatch):
    glue = FakeGlue(["READY"], {"Status": "FAILED", "ErrorMessage": "boom"})
    glue.start_crawler = lambda Name: None

    class FakeSession:
        def client(self, name):
            return glue

    monkeypatch.setattr(config, "get_session", lambda: FakeSession())
    with pytest.raises(SystemExit) as exc:
        run_crawler.main(["--wait", "--timeout", "1"])
    assert exc.value.code == 1
