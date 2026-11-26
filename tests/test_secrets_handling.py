"""The Spotify secret must never be a command-line argument or be printed."""
import io

import pytest

import deploy_all
from infra import spotify_credentials

SECRET = "not-a-real-secret-value"


class FakeStdin(io.StringIO):
    def __init__(self, tty):
        super().__init__()
        self._tty = tty

    def isatty(self):
        return self._tty


def test_credentials_come_from_env_without_prompting(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "the-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", SECRET)
    monkeypatch.setattr(spotify_credentials.getpass, "getpass", lambda prompt: pytest.fail("prompted"))

    assert spotify_credentials.get_spotify_credentials(FakeStdin(tty=True)) == ("the-id", SECRET)


def test_missing_credentials_without_terminal_fail_clearly(capsys):
    with pytest.raises(SystemExit, match="SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET"):
        spotify_credentials.get_spotify_credentials(FakeStdin(tty=False))


def test_secret_is_prompted_with_getpass_and_not_printed(monkeypatch, capsys):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "the-id")
    monkeypatch.setattr(spotify_credentials.getpass, "getpass", lambda prompt: SECRET)

    assert spotify_credentials.get_spotify_credentials(FakeStdin(tty=True)) == ("the-id", SECRET)
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_empty_prompt_answers_are_rejected(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    monkeypatch.setattr(spotify_credentials.getpass, "getpass", lambda prompt: "")
    with pytest.raises(SystemExit, match="both required"):
        spotify_credentials.get_spotify_credentials(FakeStdin(tty=True))


def test_deploy_all_never_puts_secret_on_command_line(monkeypatch, capsys):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "the-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", SECRET)
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs["env"]))
        return Done()

    monkeypatch.setattr(deploy_all.subprocess, "run", fake_run)
    deploy_all.main()

    assert calls, "no deployment steps ran"
    for cmd, env in calls:
        assert not any(SECRET in part for part in cmd)
        assert env["SPOTIFY_CLIENT_SECRET"] == SECRET  # passed via environment instead
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_deploy_all_does_not_read_credentials_json():
    source = open(deploy_all.__file__, encoding="utf-8").read()
    assert "credentials.json" not in source
