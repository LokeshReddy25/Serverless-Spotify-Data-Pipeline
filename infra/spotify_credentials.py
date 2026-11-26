"""Read the Spotify client credentials without putting them on the command line.

Order: environment variables SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET, then an interactive
prompt (the secret is read with getpass, so it is not echoed). Nothing here prints the secret.

Better option (not implemented): store the secret in AWS Secrets Manager and have the extract
Lambda read it at runtime with secretsmanager:GetSecretValue, so it never sits in the Lambda's
environment variables. See the README.
"""
import getpass
import os
import sys

ID_VAR = "SPOTIFY_CLIENT_ID"
SECRET_VAR = "SPOTIFY_CLIENT_SECRET"


def get_spotify_credentials(stdin=None):
    stdin = stdin or sys.stdin
    client_id = os.environ.get(ID_VAR, "").strip()
    client_secret = os.environ.get(SECRET_VAR, "").strip()

    if not (client_id and client_secret):
        if not stdin.isatty():
            raise SystemExit(f"ERROR: set the {ID_VAR} and {SECRET_VAR} environment variables, "
                             "or run interactively to be prompted.")
        if not client_id:
            client_id = input("Spotify client ID: ").strip()
        if not client_secret:
            client_secret = getpass.getpass("Spotify client secret (input hidden): ").strip()

    if not (client_id and client_secret):
        raise SystemExit("ERROR: a Spotify client ID and client secret are both required.")
    return client_id, client_secret
