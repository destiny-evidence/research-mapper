import logging
import os
from functools import lru_cache

from destiny_sdk.client import OAuthClient, OAuthMiddleware

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_destiny_client() -> OAuthClient:
    logger.info("Initialising Destiny OAuth client")
    base_url = os.environ["DESTINY_BASE_URL"]
    client_id = os.environ.get("DESTINY_AZURE_CLIENT_ID")
    app_id = os.environ.get("DESTINY_AZURE_APPLICATION_ID")
    secret = os.environ.get("DESTINY_AZURE_CLIENT_SECRET")
    login_url = os.environ.get("DESTINY_AZURE_LOGIN_URL")

    auth = None
    if client_id and app_id:
        auth = OAuthMiddleware(
            azure_client_id=client_id,
            azure_application_id=app_id,
            azure_client_secret=secret,
            azure_login_url=login_url,
        )
    client = OAuthClient(base_url=base_url, auth=auth)
    logger.debug("Triggering eagerly OAuth token fetch via health check")
    client.get_client().get("/v1/system/healthcheck/")
    logger.info("Destiny client authenticated and healthy")
    return client
