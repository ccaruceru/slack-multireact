# -*- coding: utf-8 -*-
"""Tests for handlers.py"""

from slack_bolt.request.async_request import AsyncBoltRequest
from multi_reaction_add.oauth.installation_store.google_cloud_storage import GoogleCloudStorageInstallationStore
import os
import sys
import json
import asyncio
import logging
import unittest
from unittest.mock import Mock, AsyncMock, patch, call

from aiohttp import web
from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_bolt.context.async_context import AsyncBoltContext
from slack_bolt.context.respond.async_respond import AsyncRespond
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient


# necessary OS env vars for handlers.py module
KEYS = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET",
        "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME", "SLACK_STATE_GOOGLE_BUCKET_NAME", "USER_DATA_BUCKET_NAME"]
# patch google storage client call and os env vars
with patch.dict(os.environ, {k:"" for k in KEYS}) as mock_env:
    with patch("google.cloud.storage.Client") as mock_storage_client:
        # importing from handlers.py is now possible
        from multi_reaction_add.handlers import warmup, save_or_display_reactions, add_reactions, handle_token_revocations, handle_uninstallations, update_home_tab


class TestHandlers(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncMock(AsyncWebClient)
        self.http_args = {"client": self.client, "http_verb": "POST", "api_url": "some-api", "req_args": {}, "headers": {}, "status_code": 200}
        patcher_app = patch("multi_reaction_add.handlers.app", spec=AsyncApp)
        self.app = patcher_app.start()
        self.app.client = self.client
        self.installation_store = AsyncMock(spec=GoogleCloudStorageInstallationStore)
        self.app.installation_store = self.installation_store

        self.ack = AsyncMock(AsyncAck)
        self.respond = AsyncMock(AsyncRespond)
        self.logger = logging.getLogger() #  TODO: make logger silent

        self.context = AsyncMock(spec=AsyncBoltContext)
        self.context.user_token = "usertoken"
        self.context.enterprise_id = "eid"
        self.context.team_id = "tid"
        self.context.is_enterprise_install = True

        self.blob = Mock(spec=Blob)
        self.blob.exists.return_value = True
        self.blob.download_as_text.return_value = 'some reactions'
        patcher_bucket = patch("multi_reaction_add.handlers.bucket", spec=Bucket)
        
        self.bucket = patcher_bucket.start()
        self.bucket.blob.return_value = self.blob

        self.addAsyncCleanup(patcher_bucket.stop)
        self.addAsyncCleanup(patcher_app.stop)

    # @classmethod
    # def setUpClass(cls):
    #     if sys.platform.startswith("win"):
    #         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def test_warmup(self):
        response = await warmup(AsyncMock(spec=web.Request))
        self.assertEqual(response.text, "")
        self.assertEqual(response.status, 200)

    @patch("multi_reaction_add.handlers.emoji_operator.get_valid_reactions")
    async def test_save_or_display_reactions(self, mock_get_valid_reactions: Mock):
        # test with reactions and enterprise_id
        mock_get_valid_reactions.return_value = ["wave", "smile"]
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "enterprise_id": "eid", "team_id": "tid", "text": ":wave: :smile:"},
            respond=self.respond,
            logger=self.logger)
        self.ack.assert_awaited_once() #  TODO: rest of the tests assert await??
        mock_get_valid_reactions.assert_called_once_with(":wave: :smile:", self.client, self.app, self.logger)
        self.bucket.blob.assert_called_once_with("/eid-tid/uid")
        self.blob.upload_from_string.assert_called_once_with("wave smile")
        self.respond.assert_called_once()
        self.assertIn("Your new reactions are saved", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with reactions and no enterprise_id
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid", "text": ":wave: :smile:"},
            respond=self.respond,
            logger=self.logger)
        self.bucket.blob.assert_called_once_with("/none-tid/uid")
        self.blob.upload_from_string.assert_called_once_with("wave smile")
        self.respond.assert_called_once()
        self.assertIn("Your new reactions are saved", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with > 23 reactions
        mock_get_valid_reactions.return_value = [f":{i}:" for i in range(30)]
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid", "text": [f":{i}:" for i in range(24)]},
            respond=self.respond,
            logger=self.logger)
        self.blob.upload_from_string.assert_not_called()
        self.respond.assert_called_once()
        self.assertIn("tried to save more than 23", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with no reactions
        mock_get_valid_reactions.return_value = []
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid", "text": "no reactions"},
            respond=self.respond,
            logger=self.logger)
        self.blob.upload_from_string.assert_not_called()
        self.respond.assert_called_once()
        self.assertIn("did not provide any valid reactions", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with no text and saved reactions
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid"},
            respond=self.respond,
            logger=self.logger)
        self.blob.upload_from_string.assert_not_called()
        self.blob.exists.assert_called_once()
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.respond.assert_called_once()
        self.assertIn("reactions are: :some: :reactions:", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with no text and no saved reactions
        self.blob.exists.return_value = False
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid"},
            respond=self.respond,
            logger=self.logger)
        self.blob.upload_from_string.assert_not_called()
        self.blob.exists.assert_called_once()
        self.blob.download_as_text.assert_not_called()
        self.respond.assert_called_once()
        self.assertIn("do not have any reactions", self.respond.call_args.args[0])

    def _reset_mocks(self):
        self.blob.reset_mock()
        self.bucket.reset_mock()
        self.respond.reset_mock()
        self.client.reset_mock()

    @patch("multi_reaction_add.handlers.EmojiOperator.get_user_reactions")
    async def test_add_reactions(self, mock_get_user_reactions: Mock):
        # test has reactions saved and enterprise id
        mock_get_user_reactions.return_value = []
        await add_reactions(ack=self.ack,
            shortcut={"user": {"id": "uid"}, "message_ts": "12345", "channel": {"id": "chid"}, "enterprise": {"id": "eid"},
                      "team": {"id": "tid"}, "trigger_id": "trid"},
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.ack.assert_called_once()
        self.bucket.blob.assert_called_once_with("/eid-tid/uid")
        self.blob.exists.assert_called_once()
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertEqual(self.client.token, "usertoken")
        mock_get_user_reactions.assert_called_once_with(self.client, "chid", "12345", "uid")
        self.client.reactions_add.assert_has_calls([
            call(channel="chid", timestamp="12345", name="some"),
            call(channel="chid", timestamp="12345", name="reactions"),
        ])

        self._reset_mocks()

        # test has reactions saved and no enterprise id
        await add_reactions(ack=self.ack,
            shortcut={"user": {"id": "uid"}, "message_ts": "12345", "channel": {"id": "chid"}, "enterprise": None,
                      "team": {"id": "tid"}, "trigger_id": "trid"},
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.bucket.blob.assert_called_once_with("/none-tid/uid")
        self.blob.exists.assert_called_once()
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.client.reactions_add.assert_has_calls([
            call(channel="chid", timestamp="12345", name="some"),
            call(channel="chid", timestamp="12345", name="reactions"),
        ])

        self._reset_mocks()

        # test has reactions saved and has user reactions
        mock_get_user_reactions.return_value = ["some"]
        await add_reactions(ack=self.ack,
            shortcut={"user": {"id": "uid"}, "message_ts": "12345", "channel": {"id": "chid"}, "enterprise": None,
                      "team": {"id": "tid"}, "trigger_id": "trid"},
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.client.reactions_add.assert_called_once_with(channel="chid", timestamp="12345", name="reactions")

        # test has reactions saved and throw slack api error
        mock_get_user_reactions.return_value = []
        self.client.reactions_add.side_effect = SlackApiError(message="", response=None)
        await add_reactions(ack=self.ack,
            shortcut={"user": {"id": "uid"}, "message_ts": "12345", "channel": {"id": "chid"}, "enterprise": None,
                      "team": {"id": "tid"}, "trigger_id": "trid"},
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.client.reactions_add.assert_has_calls([
            call(channel="chid", timestamp="12345", name="some"),
            call(channel="chid", timestamp="12345", name="reactions"),
        ])

        self._reset_mocks()

        # test has no reactions saved
        self.blob.exists.return_value = False
        await add_reactions(ack=self.ack,
            shortcut={"user": {"id": "uid"}, "message_ts": "12345", "channel": {"id": "chid"}, "enterprise": None,
                      "team": {"id": "tid"}, "trigger_id": "trid"},
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.blob.download_as_text.assert_not_called()
        self.client.reactions_add.assert_not_called()
        self.client.views_open.assert_called_once_with(trigger_id="trid",
            view=json.loads('{"type": "modal", "title": {"type": "plain_text", "text": "Multi Reaction Add"}, "close": {"type": "plain_text", "text": "Close"}, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "You do not have any reactions set :anguished:\\nType `/multireact <list of emojis>` in the chat to set one."}}]}'))

    @patch("multi_reaction_add.handlers.delete_users_data")
    async def test_handle_token_revocations(self, mock_delete_users_data: Mock):
        # test tokens are deleted
        await handle_token_revocations(event={"tokens": {"oauth": ["uid1", "uid2"], "bot": ["bot1", "bot2"]}},
            context=self.context,
            logger=self.logger)
        self.installation_store.async_delete_installation.assert_has_calls([
            call("eid", "tid", "uid1", True),
            call("eid", "tid", "uid2", True)])
        mock_delete_users_data.assert_called_once_with(self.bucket, "", "eid", "tid", ["uid1", "uid2"])
        self.installation_store.async_delete_bot.assert_called_once_with("eid", "tid", True)

        self.installation_store.reset_mock()
        mock_delete_users_data.reset_mock()

        # test no tokens are deleted
        await handle_token_revocations(event={"tokens": {"oauth": [], "bot": []}},
            context=self.context,
            logger=self.logger)
        self.installation_store.async_delete_installation.assert_not_called()
        mock_delete_users_data.assert_not_called()
        self.installation_store.assert_not_called()

    @patch("multi_reaction_add.handlers.emoji_operator.stop_emoji_update")
    async def test_handle_uninstallations(self, mock_stop_emoji_update: Mock):
        await handle_uninstallations(context=self.context, logger=self.logger)
        self.installation_store.async_delete_all.assert_called_once_with("eid", "tid", True)
        mock_stop_emoji_update.assert_called_once()

    @patch("multi_reaction_add.handlers.build_home_tab_view")
    async def test_update_home_tab(self, mock_build_home_tab_view: Mock):
        # test home tab with urls from 'host'
        mock_build_home_tab_view.return_value = "view"
        request = AsyncBoltRequest(body="", headers={"host": ["localhost"]})
        await update_home_tab(client=self.client,
            event={"user": "uid"},
            logger=self.logger,
            request=request)
        mock_build_home_tab_view.assert_called_once_with(app_url="https://localhost")
        self.client.views_publish.assert_called_once_with(user_id="uid", view="view")

        mock_build_home_tab_view.reset_mock()
        self.client.reset_mock()

        # test home tab with urls from 'Host'
        request = AsyncBoltRequest(body="", headers={"Host": ["localhost"]})
        await update_home_tab(client=self.client,
            event={"user": "uid"},
            logger=self.logger,
            request=request)
        mock_build_home_tab_view.assert_called_once_with(app_url="https://localhost")

        mock_build_home_tab_view.reset_mock()
        self.client.reset_mock()

        # test home tab without urls
        request = AsyncBoltRequest(body="")
        await update_home_tab(client=self.client,
            event={"user": "uid"},
            logger=self.logger,
            request=request)
        self.assertEqual(mock_build_home_tab_view.call_args, call())
        self.client.views_publish.assert_called_once_with(user_id="uid", view="view")
