import os
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from config import CREDENTIALS_FILE, TOKEN_FILE

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_credentials() -> Credentials:
    """Return valid OAuth2 credentials, refreshing or re-authorizing as needed."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception as e:
            logger.warning("Token refresh failed: %s — re-authorizing", e)

    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_FILE}.\n"
            "Download it from Google Cloud Console > APIs & Services > Credentials."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    logger.info("OAuth authorization complete.")
    return creds


def _save_token(creds: Credentials) -> None:
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    logger.debug("Token saved to %s", TOKEN_FILE)
