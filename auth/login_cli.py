import getpass
from dataclasses import dataclass


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


def prompt_credentials() -> Credentials:
    """Blocking terminal prompt - deliberately not a GUI window, per the
    spec's "do it in a shell" requirement for login. Called on the main
    thread before any window opens; an unknown username registers a new
    account server-side, so there's no separate "sign up" flow."""
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    return Credentials(username, password)
