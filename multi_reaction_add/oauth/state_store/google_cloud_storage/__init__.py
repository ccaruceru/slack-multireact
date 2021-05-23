#
# adaptation of https://github.com/slackapi/python-slack-sdk/blob/main/slack_sdk/oauth/state_store/amazon_s3/__init__.py
#

import logging
import time
from logging import Logger
from uuid import uuid4

from google.cloud.storage import Client

from slack_sdk.oauth.state_store.async_state_store import AsyncOAuthStateStore
from slack_sdk.oauth.state_store import OAuthStateStore


class GoogleCloudStorageOAuthStateStore(OAuthStateStore, AsyncOAuthStateStore):
    def __init__(
        self,
        *,
        storage_client: Client,
        bucket_name: str,
        expiration_seconds: int,
        logger: Logger = logging.getLogger(__name__),
    ):
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.expiration_seconds = expiration_seconds
        self._logger = logger

    @property
    def logger(self) -> Logger:
        if self._logger is None:
            self._logger = logging.getLogger(__name__)
        return self._logger

    async def async_issue(self, *args, **kwargs) -> str:
        return self.issue(*args, **kwargs)

    async def async_consume(self, state: str) -> bool:
        return self.consume(state)

    def issue(self, *args, **kwargs) -> str:
        state = str(uuid4())
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(state)
        blob.upload_from_string(str(time.time()))
        self.logger.debug("Issued %s to the Google bucket", state)
        return state

    def consume(self, state: str) -> bool:
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(state)
            body = blob.download_as_text(encoding="utf-8")

            self.logger.debug("Downloaded %s from Google bucket", state)
            created = float(body)
            expiration = created + self.expiration_seconds
            still_valid: bool = time.time() < expiration

            blob.delete()
            self.logger.debug("Deleted %s from Google bucket", state)
            return still_valid
        except Exception as e:  # skipcq: PYL-W0703
            self.logger.warning("Failed to find any persistent data for state: %s - %s", state, e)
            return False
