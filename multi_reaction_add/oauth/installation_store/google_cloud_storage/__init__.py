#
# adaptation of from https://github.com/slackapi/python-slack-sdk/blob/main/slack_sdk/oauth/installation_store/amazon_s3/__init__.py
#

import asyncio
import json
import logging
from logging import Logger
from typing import Optional

from google.cloud.storage import Client
from google.cloud.storage.bucket import Bucket


from slack_sdk.oauth.installation_store.async_installation_store import (
    AsyncInstallationStore,
)
from slack_sdk.oauth.installation_store.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models.bot import Bot
from slack_sdk.oauth.installation_store.models.installation import Installation


class GoogleCloudStorageInstallationStore(InstallationStore, AsyncInstallationStore):
    def __init__(
        self,
        *,
        storage_client: Client,
        bucket_name: str,
        client_id: str,
        logger: Logger = logging.getLogger(__name__),
    ):
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.client_id = client_id
        self._logger = logger

    @property
    def logger(self) -> Logger:
        if self._logger is None:
            self._logger = logging.getLogger(__name__)
        return self._logger

    async def async_save(self, installation: Installation):
        return self.save(installation)

    def save(self, installation: Installation):
        entity: str = json.dumps(installation.to_bot().__dict__)
        bucket = self.storage_client.bucket(self.bucket_name)
        self._save_entity(type="bot",
            entity=entity,
            bucket=bucket,
            enterprise_id=installation.enterprise_id,
            team_id=installation.team_id,
            user_id=None,
            is_enterprise_install=installation.is_enterprise_install
        )
        self.logger.debug("Uploaded %s to Google bucket as bot", entity)

        # per workspace
        entity: str = json.dumps(installation.__dict__)
        self._save_entity(type="installer",
            entity=entity,
            bucket=bucket,
            enterprise_id=installation.enterprise_id,
            team_id=installation.team_id,
            user_id=None,
            is_enterprise_install=installation.is_enterprise_install
        )
        self.logger.debug("Uploaded %s to Google bucket as installer", entity)

        # per workspace per user
        entity: str = json.dumps(installation.__dict__)
        self._save_entity(type="installer",
            entity=entity,
            bucket=bucket,
            enterprise_id=installation.enterprise_id,
            team_id=installation.team_id,
            user_id=installation.user_id or "none",
            is_enterprise_install=installation.is_enterprise_install
        )
        self.logger.debug("Uploaded %s to Google bucket as installer-%s", entity, installation.user_id)

    def _save_entity(
        self,
        type: str,
        entity: str,
        bucket: Bucket,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[str],
    ):
        key = self._key(type=type,
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )
        blob = bucket.blob(key)
        blob.upload_from_string(entity)

    async def async_find_bot(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Bot]:
        return self.find_bot(
            enterprise_id=enterprise_id,
            team_id=team_id,
            is_enterprise_install=is_enterprise_install,
        )

    def find_bot(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Bot]:
        key = self._key(type="bot",
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=None,
            is_enterprise_install=is_enterprise_install
        )
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(key)
            body = blob.download_as_text(encoding="utf-8")
            self.logger.debug("Downloaded %s from Google bucket", body)
            data = json.loads(body)
            return Bot(**data)
        except Exception as e:  # skipcq: PYL-W0703
            self.logger.warning("Failed to find bot installation data for enterprise: %s, team: %s: %s",
                                enterprise_id, team_id, e)
            return None

    async def async_find_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Installation]:
        return self.find_installation(
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install,
        )

    def find_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Installation]:
        key = self._key(type="installer",
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(key)
            body = blob.download_as_text(encoding="utf-8")
            self.logger.debug("Downloaded %s from Google bucket", body)
            data = json.loads(body)
            return Installation(**data)
        except Exception as e:  # skipcq: PYL-W0703
            self.logger.warning("Failed to find an installation data for enterprise: %s, team: %s: %s",
                                enterprise_id, team_id, e)
            return None

#
# adaptation of https://gist.github.com/seratch/d81a445ef4467b16f047156bf859cda8
#

    async def async_delete_installation(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> None:
        self.delete_installation(enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )

    def delete_installation(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> None:
        self._delete_entity(type="installer",
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )
        self.logger.debug("Uninstalled app for enterprise: %s, team: %s, user: %s",
                enterprise_id, team_id, user_id)

    async def async_delete_bot(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> None:
        self.delete_bot(enterprise_id=enterprise_id,
            team_id=team_id,
            is_enterprise_install=is_enterprise_install,
        )

    def delete_bot(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> None:
        self._delete_entity(type="bot",
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=None,
            is_enterprise_install=is_enterprise_install
        )
        self.logger.debug("Uninstalled bot for enterprise: %s, team: %s", enterprise_id, team_id)

    def _delete_entity(
        self,
        type: str,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> None:
        key = self._key(type=type,
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(key)
        if blob.exists():
            blob.delete()

    async def async_delete_all(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ):
        asyncio.gather(
            self.async_delete_bot(enterprise_id=enterprise_id, team_id=team_id,
                is_enterprise_install=is_enterprise_install
            ),
            self.async_delete_installation(
                enterprise_id=enterprise_id, team_id=team_id, user_id=None,
                is_enterprise_install=is_enterprise_install
            )
        )

    def delete_all(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ):
        self.delete_bot(enterprise_id=enterprise_id, team_id=team_id,
            is_enterprise_install=is_enterprise_install
        )
        self.delete_installation(enterprise_id=enterprise_id, team_id=team_id, user_id=None,
            is_enterprise_install=is_enterprise_install
        )

    def _key(
        self,
        type: str,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[bool] = False
    ) -> str:
        none = "none"
        e_id = enterprise_id or none
        t_id = team_id or none
        if is_enterprise_install:
            t_id = none

        workspace_path = f"{self.client_id}/{e_id}-{t_id}"
        return (
            f"{workspace_path}/{type}-{user_id}"
            if user_id
            else f"{workspace_path}/{type}"
        )
