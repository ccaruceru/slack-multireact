#
# adaptation of from https://github.com/slackapi/python-slack-sdk/blob/main/slack_sdk/oauth/installation_store/amazon_s3/__init__.py
#

import asyncio
import json
import logging
from logging import Logger
from typing import Optional

from google.cloud.storage import Client


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
        historical_data_enabled: bool = True,
        logger: Logger = logging.getLogger(__name__),
    ):
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.historical_data_enabled = historical_data_enabled
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
        none = "none"
        e_id = installation.enterprise_id or none
        t_id = installation.team_id or none
        if installation.is_enterprise_install:
            t_id = none

        workspace_path = f"{self.client_id}/{e_id}-{t_id}"

        if self.historical_data_enabled:
            history_version: str = str(installation.installed_at)
            entity: str = json.dumps(installation.to_bot().__dict__)
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(f"{workspace_path}/bot-latest")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as bot-latest", entity)
            blob = bucket.blob(f"{workspace_path}/bot-{history_version}")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as bot-%s", entity, history_version)

            # per workspace
            entity: str = json.dumps(installation.__dict__)
            blob = bucket.blob(f"{workspace_path}/installer-latest")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as installer-latest", entity)
            blob = bucket.blob(f"{workspace_path}/installer-{history_version}")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as installer-%s", entity, history_version)

            # per workspace per user
            u_id = installation.user_id or none
            entity: str = json.dumps(installation.__dict__)
            blob = bucket.blob(f"{workspace_path}/installer-{u_id}-latest")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as installer-%s-latest", entity, u_id)
            blob = bucket.blob(f"{workspace_path}/installer-{u_id}-{history_version}")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as installer-%s-%s", entity, u_id, history_version)

        else:
            entity: str = json.dumps(installation.to_bot().__dict__)
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(f"{workspace_path}/bot-latest")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as bot-latest", entity)

            # per workspace
            entity: str = json.dumps(installation.__dict__)
            blob = bucket.blob(f"{workspace_path}/installer-latest")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as installer-latest", entity)

            # per workspace per user
            u_id = installation.user_id or none
            entity: str = json.dumps(installation.__dict__)
            blob = bucket.blob(f"{workspace_path}/installer-{u_id}-latest")
            blob.upload_from_string(entity)
            self.logger.debug("Uploaded %s to Google bucket as installer-%s-latest", entity, u_id)

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
        key = self._bot_key(
            enterprise_id=enterprise_id,
            team_id=team_id,
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
        key = self._installation_key(enterprise_id=enterprise_id,
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
        key = self._installation_key(enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=user_id,
            is_enterprise_install=is_enterprise_install
        )
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(key)
        if blob.exists():
            blob.delete()
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
        key = self._bot_key(
            enterprise_id=enterprise_id,
            team_id=team_id,
            is_enterprise_install=is_enterprise_install
        )
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(key)
        if blob.exists():
            blob.delete()
            self.logger.debug("Uninstalled bot for enterprise: %s, team: %s", enterprise_id, team_id)

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

    def _installation_key(
        self,
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
            f"{workspace_path}/installer-{user_id}-latest"
            if user_id
            else f"{workspace_path}/installer-latest"
        )

    def _bot_key(
        self,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        is_enterprise_install: Optional[bool] = False
    ) -> str:
        none = "none"
        e_id = enterprise_id or none
        t_id = team_id or none
        if is_enterprise_install:
            t_id = none

        return f"{self.client_id}/{e_id}-{t_id}/bot-latest"
