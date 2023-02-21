# -*- coding: utf-8 -*-
"""Tests for handlers.py"""

import json
import logging
import unittest
from unittest.mock import Mock, AsyncMock, patch, call

from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_bolt.context.async_context import AsyncBoltContext
from slack_bolt.context.respond.async_respond import AsyncRespond
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from starlette.requests import Request

from tests.helpers import patch_import


with patch_import() as _:
    # pylint: disable=ungrouped-imports
    from multi_reaction_add.handlers import warmup, save_or_display_reactions, add_reactions,\
                                            handle_token_revocations, update_home_tab, events,\
                                            install, oauth_redirect


# pylint: disable=too-many-instance-attributes,attribute-defined-outside-init
class TestHandlers(unittest.IsolatedAsyncioTestCase):
    """Test all methods from handlers.py"""

    async def asyncSetUp(self):
        """Setup tests"""
        self.client = AsyncMock(AsyncWebClient)
        self.http_args = {"client": self.client, "http_verb": "POST", "api_url": "some-api", "req_args": {},
            "headers": {}, "status_code": 200}
        self.ack = AsyncMock(AsyncAck)
        self.respond = AsyncMock(AsyncRespond)
        self.logger = logging.getLogger()
        self.logger.handlers = []

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
        # self.addAsyncCleanup(patcher_app.stop)

    async def test_warmup(self):
        """Test warmup http call"""
        response = await warmup(None)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.status_code, 200)

    @patch("multi_reaction_add.handlers.EmojiOperator.get_valid_reactions")
    async def test_save_or_display_reactions(self, get_valid_reactions: AsyncMock):
        """Test save_or_display_reactions method"""

        # test with reactions and enterprise_id
        get_valid_reactions.return_value = ["wave", "smile"]
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "enterprise_id": "eid", "team_id": "tid", "text": ":wave: :smile:"},
            respond=self.respond,
            logger=self.logger)
        self.ack.assert_awaited_once()
        get_valid_reactions.assert_awaited_once_with(":wave: :smile:", self.client, self.logger)
        self.bucket.blob.assert_called_once_with("/eid-tid/uid")
        self.blob.upload_from_string.assert_called_once_with("wave smile")
        self.respond.assert_awaited_once()
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
        self.respond.assert_awaited_once()
        self.assertIn("Your new reactions are saved", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with > 23 reactions
        get_valid_reactions.return_value = [f":{i}:" for i in range(30)]
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid", "text": " ".join([f":{i}:" for i in range(24)])},
            respond=self.respond,
            logger=self.logger)
        self.blob.upload_from_string.assert_not_called()
        self.respond.assert_awaited_once()
        self.assertIn("tried to save more than 23", self.respond.call_args.args[0])

        self._reset_mocks()

        # test with no reactions
        get_valid_reactions.return_value = []
        await save_or_display_reactions(ack=self.ack,
            client=self.client,
            command={"user_id": "uid", "team_id": "tid", "text": "no reactions"},
            respond=self.respond,
            logger=self.logger)
        self.blob.upload_from_string.assert_not_called()
        self.respond.assert_awaited_once()
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
        self.respond.assert_awaited_once()
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
        self.respond.assert_awaited_once()
        self.assertIn("do not have any reactions", self.respond.call_args.args[0])

    def _reset_mocks(self):
        self.blob.reset_mock()
        self.bucket.reset_mock()
        self.respond.reset_mock()
        self.client.reset_mock()

    @patch("multi_reaction_add.handlers.EmojiOperator.get_user_reactions")
    async def test_add_reactions(self, get_user_reactions: AsyncMock):
        """Test add_reactions method"""

        # test has reactions saved and enterprise id
        shortcut = {
            "user": {"id": "uid"},
            "message_ts": "12345",
            "channel": {"id": "chid"},
            "enterprise": None,
            "team": {"id": "tid"},
            "trigger_id": "trid"
        }
        get_user_reactions.return_value = []
        await add_reactions(ack=self.ack,
            shortcut={**shortcut, **{"enterprise": {"id": "eid"}}},
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.ack.assert_awaited_once()
        self.bucket.blob.assert_called_once_with("/eid-tid/uid")
        self.blob.exists.assert_called_once()
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.assertEqual(self.client.token, "usertoken")
        get_user_reactions.assert_awaited_once_with(self.client, "chid", "12345", "uid")
        self.client.reactions_add.assert_has_awaits([
            call(channel="chid", timestamp="12345", name="some"),
            call(channel="chid", timestamp="12345", name="reactions"),
        ])

        self._reset_mocks()

        # test has reactions saved and no enterprise id
        await add_reactions(ack=self.ack,
            shortcut=shortcut,
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.bucket.blob.assert_called_once_with("/none-tid/uid")
        self.blob.exists.assert_called_once()
        self.blob.download_as_text.assert_called_once_with(encoding="utf-8")
        self.client.reactions_add.assert_has_awaits([
            call(channel="chid", timestamp="12345", name="some"),
            call(channel="chid", timestamp="12345", name="reactions"),
        ])

        self._reset_mocks()

        # test has reactions saved and has user reactions
        get_user_reactions.return_value = ["some"]
        await add_reactions(ack=self.ack,
            shortcut=shortcut,
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.client.reactions_add.assert_awaited_once_with(channel="chid", timestamp="12345", name="reactions")

        # test has reactions saved and throw slack api error
        get_user_reactions.return_value = []
        self.client.reactions_add.side_effect = SlackApiError(message="", response=None)
        await add_reactions(ack=self.ack,
            shortcut=shortcut,
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.client.reactions_add.assert_has_awaits([
            call(channel="chid", timestamp="12345", name="some"),
            call(channel="chid", timestamp="12345", name="reactions"),
        ])

        self._reset_mocks()

        # test has no reactions saved
        self.blob.exists.return_value = False
        await add_reactions(ack=self.ack,
            shortcut=shortcut,
            client=self.client,
            logger=self.logger,
            context=self.context)
        self.blob.download_as_text.assert_not_called()
        self.client.reactions_add.assert_not_called()
        self.client.views_open.assert_awaited_once_with(trigger_id="trid",
            view=json.loads('{"type": "modal", "title": {"type": "plain_text", "text": "Multi Reaction Add"}, "close":'
                            ' {"type": "plain_text", "text": "Close"}, "blocks": [{"type": "section", "text": {"type":'
                            ' "mrkdwn", "text": "You do not have any reactions set :anguished:\\nType `/multireact'
                            ' <list of emojis>` in the chat to set one."}}]}'))

    @patch("multi_reaction_add.handlers.delete_users_data")
    async def test_handle_token_revocations(self, delete_users_data: AsyncMock):
        """Test handle_token_revocations method"""
        # test tokens are deleted
        await handle_token_revocations(event={"tokens": {"oauth": ["uid1", "uid2"], "bot": ["bot1", "bot2"]}},
            context=self.context,
            logger=self.logger)
        delete_users_data.assert_awaited_once_with(self.bucket, "", "eid", "tid", ["uid1", "uid2"])

        delete_users_data.reset_mock()

        # test no tokens are deleted
        await handle_token_revocations(event={"tokens": {"oauth": [], "bot": []}},
            context=self.context,
            logger=self.logger)
        delete_users_data.assert_not_awaited()

    @patch("multi_reaction_add.handlers.build_home_tab_view")
    async def test_update_home_tab(self, build_home_tab_view: Mock):
        """Test update_home_tab method"""

        # test home tab with urls from 'host'
        build_home_tab_view.return_value = "view"
        request = AsyncBoltRequest(body="", headers={"host": ["host1"]})
        await update_home_tab(client=self.client,
            event={"user": "uid"},
            logger=self.logger,
            request=request)
        build_home_tab_view.assert_called_once_with(app_url="https://host1")
        self.client.views_publish.assert_awaited_once_with(user_id="uid", view="view")

        build_home_tab_view.reset_mock()
        self.client.reset_mock()

        # test home tab without urls
        request = AsyncBoltRequest(body="")
        await update_home_tab(client=self.client,
            event={"user": "uid"},
            logger=self.logger,
            request=request)
        self.assertEqual(build_home_tab_view.call_args, call())
        self.client.views_publish.assert_awaited_once_with(user_id="uid", view="view")

    @patch.dict("os.environ", {"SLACK_CLIENT_ID": "", "SLACK_CLIENT_SECRET": ""})
    async def test_main_endpoints(self):
        """Test if main route endpoints do respond"""
        async def receive():
            return {"type": "http.request", "body": b""}

        app = AsyncApp()
        app._async_middleware_list = []  # pylint: disable=protected-access
        app.oauth_flow.settings.state_validation_enabled = False
        app_handler = AsyncSlackRequestHandler(app)
        with patch("multi_reaction_add.handlers.app_handler", app_handler):
            with patch.multiple(app.oauth_flow, run_installation=AsyncMock(), store_installation=AsyncMock()):
                tests = [("POST", "/slack/events", "", events), ("GET", "/slack/install", "", install),
                         ("GET", "/slack/oauth_redirect", b"code=123", oauth_redirect)]
                for method, path, query, function in tests:
                    scope = {"type": "http", "method": method, "path": path, "headers": {}, "query_string": query}
                    request = Request(scope=scope, receive=receive)
                    response = await function(request)
                    self.assertEqual(response.status_code, 200)
