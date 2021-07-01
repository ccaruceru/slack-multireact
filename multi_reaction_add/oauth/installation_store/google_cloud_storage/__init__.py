# -*- coding: utf-8 -*-
"""Store Slack bot install data to a Google Cloud Storage bucket.

Adapted from https://github.com/slackapi/python-slack-sdk/blob/main/slack_sdk/oauth/installation_store/amazon_s3/__init__.py # pylint: disable=line-too-long
"""

import asyncio
import json
import logging
from logging import Logger
from typing import Optional

from google.cloud.storage import Client
from google.cloud.storage.bucket import Bucket
from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore
from slack_sdk.oauth.installation_store.installation_store import InstallationStore
from slack_sdk.oauth.installation_store.models.bot import Bot
from slack_sdk.oauth.installation_store.models.installation import Installation


class GoogleCloudStorageInstallationStore(InstallationStore, AsyncInstallationStore):
    """Store Slack user installation data to a Google Cloud Storage bucket.

    https://api.slack.com/authentication/oauth-v2

    Attributes:
        storage_client (Client): A Google Cloud Storage client to access the bucket
        bucket_name (str): Bucket to store user installation data for current Slack app
        client_id (str): Slack application client id
    """
    def __init__(
        self,
        *,
        storage_client: Client,
        bucket_name: str,
        client_id: str,
        logger: Logger = logging.getLogger(__name__),
    ):
        """Creates a new instance.

        Args:
            storage_client (Client): A Google Cloud Storage client to access the bucket
            bucket_name (str): Bucket to store user installation data for current Slack app
            client_id (str): Slack application client id
            logger (Logger): Custom logger for logging. Defaults to a new logger for this module.
        """
        self.storage_client = storage_client
        self.bucket_name = bucket_name
        self.client_id = client_id
        self._logger = logger

    @property
    def logger(self) -> Logger:
        """Gets the internal logger if it exists, otherwise creates a new one.

        Returns:
            Logger: the logger
        """
        if self._logger is None:
            self._logger = logging.getLogger(__name__)
        return self._logger

    async def async_save(self, installation: Installation):
        """Save user's app authorization.

        Args:
            installation (Installation): information about the user and the app usage authorization
        """
        self.save(installation)

    def save(self, installation: Installation):
        """Save user's app authorization.

        Args:
            installation (Installation): information about the user and the app usage authorization
        """
        entity: str = json.dumps(installation.to_bot().__dict__)
        bucket = self.storage_client.bucket(self.bucket_name)
        self._save_entity(data_type="bot",
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
        self._save_entity(data_type="installer",
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
        self._save_entity(data_type="installer",
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
        data_type: str,
        entity: str,
        bucket: Bucket,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[str],
    ):
        """Saves data to a GCS bucket.

        Args:
            data_type (str): data type
            entity (str): data payload
            bucket (Bucket): GCS Bucket
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid
        """
        key = self._key(data_type=data_type,
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
        """Check if a Slack bot user has been installed in a Slack workspace.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False.

        Returns:
            Optional[Bot]: A Slack bot/app identifier object if found, else None
        """
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
        """Check if a Slack bot user has been installed in a Slack workspace.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False

        Returns:
            Optional[Bot]: A Slack bot/app identifier object if found, else None
        """
        key = self._key(data_type="bot",
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
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Failed to find bot installation data for enterprise: %s, team: %s: %s",
                                enterprise_id, team_id, exc)
            return None

    async def async_find_installation(
        self,
        *,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str] = None,
        is_enterprise_install: Optional[bool] = False,
    ) -> Optional[Installation]:
        """Check if a Slack user has installed the app.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID. Defaults to None.
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False

        Returns:
            Optional[Installation]: A installation identifier object if found, else None
        """
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
        """Check if a Slack user has installed the app.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID. Defaults to None.
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False

        Returns:
            Optional[Installation]: A installation identifier object if found, else None
        """
        key = self._key(data_type="installer",
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
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Failed to find an installation data for enterprise: %s, team: %s: %s",
                                enterprise_id, team_id, exc)
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
        """Deletes a user's Slack installation data.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
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
        """Deletes a user's Slack installation data.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
        self._delete_entity(data_type="installer",
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
        """Deletes Slack bot user install data from the workspace.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
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
        """Deletes Slack bot user install data from the workspace.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
        self._delete_entity(data_type="bot",
            enterprise_id=enterprise_id,
            team_id=team_id,
            user_id=None,
            is_enterprise_install=is_enterprise_install
        )
        self.logger.debug("Uninstalled bot for enterprise: %s, team: %s", enterprise_id, team_id)

    def _delete_entity(
        self,
        data_type: str,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[bool] = False,
    ) -> None:
        """Deletes an object from a Google Cloud Storage bucket.

        Args:
            data_type (str): data type
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
        key = self._key(data_type=data_type,
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
        """Deletes all users and bot installation data.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
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
        """Deletes all users and bot installation data.

        Args:
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False
        """
        self.delete_bot(enterprise_id=enterprise_id, team_id=team_id,
            is_enterprise_install=is_enterprise_install
        )
        self.delete_installation(enterprise_id=enterprise_id, team_id=team_id, user_id=None,
            is_enterprise_install=is_enterprise_install
        )

    def _key(
        self,
        data_type: str,
        enterprise_id: Optional[str],
        team_id: Optional[str],
        user_id: Optional[str],
        is_enterprise_install: Optional[bool] = False
    ) -> str:
        """Helper method to create a path to an object in a GCS bucket.

        Args:
            data_type (str): object type
            enterprise_id (Optional[str]): Slack Enterprise Grid ID
            team_id (Optional[str]): Slack workspace/team ID
            user_id (Optional[str]): Slack user ID
            is_enterprise_install (Optional[str]): True if the Slack app is installed across multiple workspaces in an
                                                   Enterprise Grid. Defaults to False

        Returns:
            str: path to data corresponding to input args
        """
        none = "none"
        e_id = enterprise_id or none
        t_id = team_id or none
        if is_enterprise_install:
            t_id = none

        workspace_path = f"{self.client_id}/{e_id}-{t_id}"
        return (
            f"{workspace_path}/{data_type}-{user_id}"
            if user_id
            else f"{workspace_path}/{data_type}"
        )
