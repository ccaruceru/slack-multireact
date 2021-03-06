# -*- coding: utf-8 -*-
"""Tests for oauth/state_store/google_cloud_storage/__init__.py"""

import time
import logging
import unittest
from unittest.mock import Mock

from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket
from google.cloud.storage.client import Client

from multi_reaction_add.oauth.state_store.google_cloud_storage import GoogleCloudStorageOAuthStateStore

# pylint: disable=attribute-defined-outside-init
class TestGoogleStateStore(unittest.IsolatedAsyncioTestCase):
    """Test GoogleCloudStorageOAuthStateStore class"""

    async def asyncSetUp(self):
        """Setup tests"""
        self.blob = Mock(spec=Blob)
        self.blob.download_as_text.return_value = str(time.time())

        self.bucket = Mock(spec=Bucket)
        self.bucket.blob.return_value = self.blob

        self.storage_client = Mock(spec=Client)
        self.storage_client.bucket.return_value = self.bucket

        self.logger = logging.getLogger()
        self.logger.handlers = []

        self.bucket_name = "bucket"
        self.state_store = GoogleCloudStorageOAuthStateStore(storage_client=self.storage_client,
            bucket_name=self.bucket_name,
            expiration_seconds=10,
            logger=self.logger
        )

    def test_get_logger(self):
        """Test get_logger method"""
        self.assertEqual(self.state_store.logger, self.logger)


    async def test_async_issue(self):
        """Test async_issue method"""
        state = await self.state_store.async_issue()
        self.storage_client.bucket.assert_called_once_with(self.bucket_name)
        self.bucket.blob.assert_called_once()
        self.assertEqual(self.bucket.blob.call_args.args[0], state)
        self.blob.upload_from_string.assert_called_once()
        self.assertRegex(self.blob.upload_from_string.call_args.args[0], r"\d{10,}.\d{5,}")

    async def test_async_comsume(self):
        """Test async_comsume method"""
        state = "state"
        # test consume returns valid
        valid = await self.state_store.async_consume(state=state)
        self.storage_client.bucket.assert_called_once_with(self.bucket_name)
        self.bucket.blob.assert_called_once_with(state)
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertTrue(
            time.time() < float(self.blob.download_as_text.return_value) + self.state_store.expiration_seconds)
        self.blob.delete.assert_called_once()
        self.assertTrue(valid)

        self.blob.reset_mock()

        # test consume returns invalid
        self.state_store.expiration_seconds = 0
        valid = await self.state_store.async_consume(state=state)
        self.assertFalse(
            time.time() < float(self.blob.download_as_text.return_value) + self.state_store.expiration_seconds)
        self.assertFalse(valid)

        self.blob.reset_mock()

        # test consume throw exception
        self.blob.download_as_text.side_effect = Exception()
        valid = await self.state_store.async_consume(state=state)
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertFalse(valid)
