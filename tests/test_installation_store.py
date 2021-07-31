# -*- coding: utf-8 -*-
"""Tests for oauth/installation_store/google_cloud_storage/__init__.py"""

import json
import time
import logging
import unittest
from unittest.mock import Mock, AsyncMock, call, patch
from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket

from google.cloud.storage.client import Client
from slack_sdk.oauth.installation_store.models.installation import Installation

from multi_reaction_add.oauth.installation_store.google_cloud_storage import GoogleCloudStorageInstallationStore

class TestGoogleInstallationStore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.blob = Mock(spec=Blob)
        self.bucket = Mock(spec=Bucket)
        self.bucket.blob.return_value = self.blob

        self.storage_client = Mock(spec=Client)
        self.storage_client.bucket.return_value = self.bucket

        self.bucket_name = "bucket"
        self.client_id = "clid"
        self.logger = logging.getLogger()
        self.logger.handlers = []

        self.installation_store = GoogleCloudStorageInstallationStore(storage_client=self.storage_client,
            bucket_name=self.bucket_name,
            client_id=self.client_id,
            logger=self.logger)

        self.installation = Installation(user_id="uid",
            team_id="tid",
            is_enterprise_install=True,
            enterprise_id="eid")

    def test_get_logger(self):
        self.assertEqual(self.installation_store.logger, self.logger)

    @patch("multi_reaction_add.oauth.installation_store.google_cloud_storage.GoogleCloudStorageInstallationStore._save_entity")
    async def test_async_save(self, save_entity: Mock):
        await self.installation_store.async_save(self.installation)
        self.storage_client.bucket.assert_called_once_with(self.bucket_name)
        save_entity.assert_has_calls([
            call(data_type="bot",
                 entity=json.dumps(self.installation.to_bot().__dict__),
                 bucket=self.bucket,
                 enterprise_id=self.installation.enterprise_id,
                 team_id=self.installation.team_id,
                 user_id=None,
                 is_enterprise_install=self.installation.is_enterprise_install),
            call(data_type="installer",
                 entity=json.dumps(self.installation.__dict__),
                 bucket=self.bucket,
                 enterprise_id=self.installation.enterprise_id,
                 team_id=self.installation.team_id,
                 user_id=None,
                 is_enterprise_install=self.installation.is_enterprise_install),
            call(data_type="installer",
                 entity=json.dumps(self.installation.__dict__),
                 bucket=self.bucket,
                 enterprise_id=self.installation.enterprise_id,
                 team_id=self.installation.team_id,
                 user_id=self.installation.user_id,
                 is_enterprise_install=self.installation.is_enterprise_install)
        ])

    def test_save_entity_and_test_key(self):
        entity = "some data"
        # test upload user data enterprise install
        self.installation_store._save_entity(data_type="dtype",
            entity=entity,
            bucket=self.bucket,
            enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=self.installation.user_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.bucket.blob.assert_called_once_with(
            f"{self.client_id}/{self.installation.enterprise_id}-none/dtype-{self.installation.user_id}")
        self.blob.upload_from_string.assert_called_once_with(entity)

        self.bucket.reset_mock()

        # test upload user data normal install
        self.installation_store._save_entity(data_type="dtype",
            entity=entity,
            bucket=self.bucket,
            enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=self.installation.user_id,
            is_enterprise_install=False)
        self.bucket.blob.assert_called_once_with(
            f"{self.client_id}/{self.installation.enterprise_id}-{self.installation.team_id}/dtype-{self.installation.user_id}")

        self.bucket.reset_mock()

        # test upload bot data
        self.installation_store._save_entity(data_type="dtype",
            entity=entity,
            bucket=self.bucket,
            enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=None,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.bucket.blob.assert_called_once_with(
            f"{self.client_id}/{self.installation.enterprise_id}-none/dtype")

    async def test_async_find_bot(self):
        self.blob.download_as_text.return_value = json.dumps({"bot_token": "xoxb-token",
            "bot_id": "bid",
            "bot_user_id": "buid",
            "installed_at": time.time()})

        # test bot found
        bot = await self.installation_store.async_find_bot(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.storage_client.bucket.assert_called_once_with(self.bucket_name)
        self.bucket.blob.assert_called_once_with(f"{self.client_id}/{self.installation.enterprise_id}-none/bot")
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertIsNotNone(bot)
        self.assertEqual(bot.bot_token, "xoxb-token")

        self.blob.reset_mock()

        # test bot not found
        self.blob.download_as_text.side_effect = Exception()
        bot = await self.installation_store.async_find_bot(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertIsNone(bot)

    async def test_async_find_installation(self):
        self.blob.download_as_text.return_value = json.dumps({"user_id": self.installation.user_id})

        # test installation found
        installation = await self.installation_store.async_find_installation(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=self.installation.user_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.storage_client.bucket.assert_called_once_with(self.bucket_name)
        self.bucket.blob.assert_called_once_with(
            f"{self.client_id}/{self.installation.enterprise_id}-none/installer-{self.installation.user_id}")
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertIsNotNone(installation)
        self.assertEqual(installation.user_id, self.installation.user_id)

        self.blob.reset_mock()

        # test installation not found
        self.blob.download_as_text.side_effect = Exception()
        installation = await self.installation_store.async_find_installation(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=self.installation.user_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertIsNone(installation)

    async def test_async_delete_installation_and_test_delete_entity(self):
        # test delete blob exist
        self.blob.exists.return_value = True
        await self.installation_store.async_delete_installation(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=self.installation.user_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.storage_client.bucket.assert_called_once_with(self.bucket_name)
        self.bucket.blob.assert_called_once_with(
            f"{self.client_id}/{self.installation.enterprise_id}-none/installer-{self.installation.user_id}")
        self.blob.exists.assert_called_once()
        self.blob.delete.assert_called_once()

        self.blob.reset_mock()

        # test delete blob doesn't exist
        self.blob.exists.return_value = False
        await self.installation_store.async_delete_installation(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=self.installation.user_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        self.blob.exists.assert_called_once()
        self.blob.delete.assert_not_called()

    @patch("multi_reaction_add.oauth.installation_store.google_cloud_storage.GoogleCloudStorageInstallationStore._delete_entity")
    async def test_async_delete_bot(self, delete_entity: Mock):
        await self.installation_store.async_delete_bot(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        delete_entity.assert_called_once_with(data_type="bot",
            enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            user_id=None,
            is_enterprise_install=self.installation.is_enterprise_install)

    @patch("multi_reaction_add.oauth.installation_store.google_cloud_storage.GoogleCloudStorageInstallationStore.async_delete_bot")
    @patch("multi_reaction_add.oauth.installation_store.google_cloud_storage.GoogleCloudStorageInstallationStore.async_delete_installation")
    async def test_async_delete_all(self, async_delete_installation: AsyncMock, async_delete_bot: AsyncMock):
        await self.installation_store.async_delete_all(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        async_delete_bot.assert_called_once_with(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        async_delete_installation.assert_called_once_with(enterprise_id=self.installation.enterprise_id,
            user_id=None,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)

    @patch("multi_reaction_add.oauth.installation_store.google_cloud_storage.GoogleCloudStorageInstallationStore.delete_bot")
    @patch("multi_reaction_add.oauth.installation_store.google_cloud_storage.GoogleCloudStorageInstallationStore.delete_installation")
    def test_delete_all(self, delete_installation: Mock, delete_bot: Mock):
        self.installation_store.delete_all(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        delete_bot.assert_called_once_with(enterprise_id=self.installation.enterprise_id,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
        delete_installation.assert_called_once_with(enterprise_id=self.installation.enterprise_id,
            user_id=None,
            team_id=self.installation.team_id,
            is_enterprise_install=self.installation.is_enterprise_install)
