"""The Spotify secret must never be a command-line argument or be printed."""
import io

import pytest

import deploy_all
from infra import setup_lambda, spotify_credentials

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


@pytest.mark.parametrize("main", [deploy_all.main, setup_lambda.main])
def test_scripts_reject_secret_command_line_arguments(main, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--bucket-name", "b", "--client-secret", SECRET])
    assert exc.value.code == 2  # argparse: unrecognized argument


def test_deploy_all_does_not_read_credentials_json():
    source = open(deploy_all.__file__, encoding="utf-8").read()
    assert "open(" not in source and "subprocess" not in source
