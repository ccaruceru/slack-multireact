# -*- coding: utf-8 -*-
"""Tests for internals.py"""
import os
import json
import sys
import unittest
import asyncio
import logging
from datetime import datetime, timedelta
from io import StringIO
from importlib import reload
from unittest.mock import AsyncMock, Mock, call, patch

from aiohttp.client_exceptions import ClientConnectorError
from google.cloud.storage.blob import Blob
from google.cloud.storage.bucket import Bucket
from slack_bolt.app.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.web.async_slack_response import AsyncSlackResponse

from multi_reaction_add.internals import check_env, setup_logger, build_home_tab_view, user_data_key,\
                                         delete_users_data, EmojiOperator


# pylint: disable=attribute-defined-outside-init
class TestCheckEnv(unittest.TestCase):
    """Test env vars checker"""

    def setUp(self):
        """Setup tests"""
        self.env_keys = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET",
                "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME", "SLACK_STATE_GOOGLE_BUCKET_NAME", "USER_DATA_BUCKET_NAME"]

    def test_checkenv_ok(self):
        """Test checkenv success"""
        for key in self.env_keys:
            os.environ[key] = ""

        check_env()
        for key in self.env_keys:
            del os.environ[key]

    @unittest.expectedFailure
    def test_checkenv_missing(self):
        """Test checkenv throws error"""
        check_env()


class TestCloudLogging(unittest.TestCase):
    """Test logger class"""

    def tearDown(self):
        """Cleanup tests"""
        logging.shutdown()
        reload(logging)

    def test_log_format(self):
        """Test logger has correct format"""
        with StringIO() as stream:
            logger = setup_logger(stream=stream)
            logger.info("a message")
            self.assertRegex(stream.getvalue(), r'{"timestamp": "\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}", '
                                                 '"severity": "INFO", "funcName": "test_log_format", '
                                                 '"component": "root", "message": "a message"}')

    def test_log_level_set(self):
        """Test log level can be set from env"""
        os.environ["UVICORN_LOG_LEVEL"] = "WARNING"
        with StringIO() as stream:
            logger = setup_logger(stream=stream)
            del os.environ["UVICORN_LOG_LEVEL"]
            logger.info("a message")
            logger.warning("some message")
            logger.error("another message")
            output = stream.getvalue()
            self.assertTrue(all([
                "a message" not in output,
                "some message" in output,
                "another message" in output
            ]), msg="Cannot set log level")


class TestInternals(unittest.TestCase):
    """Test light methods"""

    def test_build_home_tab(self):
        """Test build_home_tab method"""

        # check home tab with no urls
        home_tab_dict = build_home_tab_view()
        home_tab_json = json.dumps(home_tab_dict, separators=(",", ":"))
        self.assertEqual(home_tab_json, '{"type":"home","blocks":[{"type":"header","text":{"type":"plain_text","text":'
                                        '"Setting emojis :floppy_disk:","emoji":true}},{"type":"section","text":{"type"'
                                        ':"mrkdwn","text":"Type `/multireact <list of emojis>` in any chat to set a'
                                        ' list of emojis for later usage."}},{"type":"section","text":{"type":"mrkdwn",'
                                        '"text":"You can view what you saved any moment by typing `/multireact` in'
                                        ' any chat."}},{"type":"divider"},{"type":"header","text":{"type":"plain_text",'
                                        '"text":"Adding Reactions :star-struck:","emoji":true}},{"type":"section",'
                                        '"text":{"type":"mrkdwn","text":"Go to a message, click `More Actions`, then'
                                        ' click on `Multireact` to react with the saved emojis to the message.\\n\\nIf'
                                        ' you can\'t see `Multireact`, click `More message shortcuts...`'
                                        ' to find it."}}]}')

        # check home tab with urls
        home_tab_dict = build_home_tab_view(app_url="localhost")
        home_tab_json = json.dumps(home_tab_dict, separators=(",", ":"))
        self.assertEqual(home_tab_json, '{"type":"home","blocks":[{"type":"header","text":{"type":"plain_text","text":'
                                        '"Setting emojis :floppy_disk:","emoji":true}},{"type":"section","text":{"type"'
                                        ':"mrkdwn","text":"Type `/multireact <list of emojis>` in any chat to set a'
                                        ' list of emojis for later usage."}},{"type":"image","image_url":'
                                        '"localhost/img/reaction-write-emojis.png?w=1024&ssl=1","alt_text":'
                                        '"write emojis"},{"type":"image","image_url":'
                                        '"localhost/img/reaction-save.png?w=1024&ssl=1","alt_text":'
                                        '"saved emojis"},{"type":"section","text":{"type":"mrkdwn","text":'
                                        '"You can view what you saved any moment by typing `/multireact` in any'
                                        ' chat."}},{"type":"image","image_url":'
                                        '"localhost/img/reaction-write-nothing.png?w=1024&ssl=1","alt_text":'
                                        '"view emojis"},{"type":"image","image_url":'
                                        '"localhost/img/reaction-view.png?w=1024&ssl=1","alt_text":"view emojis"},'
                                        '{"type":"divider"},{"type":"header","text":{"type":"plain_text","text":'
                                        '"Adding Reactions :star-struck:","emoji":true}},{"type":"section","text":'
                                        '{"type":"mrkdwn","text":"Go to a message, click `More Actions`, then click on'
                                        ' `Multireact` to react with the saved emojis to the message.\\n\\nIf you'
                                        ' can\'t see `Multireact`, click `More message shortcuts...` to find it."}},'
                                        '{"type":"image","image_url":'
                                        '"localhost/img/reaction-none.png?w=1024&ssl=1","alt_text":"message with no'
                                        ' reactions"},{"type":"image","image_url":'
                                        '"localhost/img/reaction-menu.png?w=1024&ssl=1","alt_text":"message menu"},'
                                        '{"type":"image","image_url":'
                                        '"localhost/img/reaction-add.png?w=1024&ssl=1","alt_text":'
                                        '"message with reactions"}]}')

    def test_user_data_key(self):
        """Test user_data_key method"""
        self.assertEqual(
            user_data_key("client_id", "enter_id", "team_id", "user_id"),
            "client_id/enter_id-team_id/user_id")
        self.assertEqual(
            user_data_key("client_id", None, "team_id", "user_id"),
            "client_id/none-team_id/user_id")


class TestDeleteUserData(unittest.IsolatedAsyncioTestCase):
    """Test user data deletion"""

    async def asyncSetUp(self):
        """Setup tests"""
        self.bucket = Mock(spec=Bucket)
        self.blob = Blob(name="name", bucket=self.bucket)
        self.blob.delete = Mock()
        self.bucket.blob = Mock(return_value=self.blob)

    @classmethod
    def setUpClass(cls):
        """Setup tests once"""
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    @patch("multi_reaction_add.internals.user_data_key")
    async def test_delete_users_data(self, mock_user_data_key: Mock):
        """Test delete_users_data method"""

        # test user data exists
        self.blob.exists = Mock(return_value=True)
        await delete_users_data(self.bucket, "client_id", "enter_id", "team_id", ["user_id"])
        self.blob.exists.assert_called_once()
        self.blob.delete.assert_called_once()

        self.blob.delete.reset_mock()

        # test user data doesn't exist
        self.blob.exists = Mock(return_value=False)
        await delete_users_data(self.bucket, "client_id", "enter_id", "team_id", ["user_id"])
        self.blob.exists.assert_called_once()
        self.blob.delete.assert_not_called()

        # test multiple user data
        await delete_users_data(self.bucket, "client_id", "enter_id", "team_id", ["user_id1", "user_id2"])
        mock_user_data_key.assert_has_calls([call(slack_client_id="client_id",
                                             enterprise_id="enter_id",
                                             team_id="team_id",
                                             user_id="user_id1"),
                                        call(slack_client_id="client_id",
                                             enterprise_id="enter_id",
                                             team_id="team_id",
                                             user_id="user_id2")])


class TestEmojiOperator(unittest.IsolatedAsyncioTestCase):
    """Test EmojiOperator class"""
    # pylint: disable=protected-access

    async def asyncSetUp(self):
        """Setup tests"""
        self.client = AsyncMock(AsyncWebClient)
        self.http_args = {"client": self.client, "http_verb": "POST", "api_url": "some-api", "req_args": {},
            "headers": {}, "status_code": 200}
        self.app = AsyncMock(AsyncApp)
        self.app.client = self.client
        self.logger = logging.getLogger()
        self.logger.handlers = []

    @classmethod
    def setUpClass(cls):
        """Setup tests once"""
        if sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def asyncTearDown(self):
        """Cleanup tests"""
        EmojiOperator._all_emojis = []

    async def test_get_user_reactions(self):
        """Test get_user_reactions method"""

        # check no reactions
        response = AsyncSlackResponse(**{**self.http_args, **{"data": {"type": "message", "message": {}}} })
        self.client.reactions_get.return_value = response
        emojis = await EmojiOperator.get_user_reactions(client=self.client,
            channel_id="channel_id",
            message_ts="message_ts",
            user_id="user_id")
        self.assertListEqual(emojis, [])

        # sample response: https://api.slack.com/methods/reactions.get
        # check reactions on message
        response = AsyncSlackResponse(**{**self.http_args, **{"data": {"type": "message", "message": {
            "reactions": [{
                    "name": "smile",
                    "users": [ "user_id1", "user_id2" ]
                }, {
                    "name": "wink",
                    "users": [ "user_id2", "user_id3" ]
                }]
        }}}})
        self.client.reactions_get.return_value = response
        emojis = await EmojiOperator.get_user_reactions(client=self.client,
            channel_id="channel_id",
            message_ts="message_ts",
            user_id="user_id2")
        self.assertListEqual(emojis, ["smile", "wink"])

        # check reactions on file
        response = AsyncSlackResponse(**{**self.http_args, **{"data": {"type": "file", "file": {
            "reactions": [{
                    "name": "laugh",
                    "users": [ "user_id1", "user_id2" ]
                }]
        }}}})
        self.client.reactions_get.return_value = response
        emojis = await EmojiOperator.get_user_reactions(client=self.client,
            channel_id="channel_id",
            message_ts="message_ts",
            user_id="user_id1")
        self.assertListEqual(emojis, ["laugh"])

        # check reactions on file_comment
        response = AsyncSlackResponse(**{**self.http_args, **{"data": {"type": "file_comment", "comment": {
            "reactions": [{
                    "name": "heart",
                    "users": [ "user_id1", "user_id2" ]
                }]
        }}}})
        self.client.reactions_get.return_value = response
        emojis = await EmojiOperator.get_user_reactions(client=self.client,
            channel_id="channel_id",
            message_ts="message_ts",
            user_id="user_id2")
        self.assertListEqual(emojis, ["heart"])

    @patch("aiohttp.ClientSession.get")
    async def test_get_reactions_in_team(self, get: AsyncMock):
        """Test get_reactions_in_team method"""
        mock_context_manager: AsyncMock = get.return_value.__aenter__.return_value
        mock_context_manager.status = 200
        mock_context_manager.text.return_value = \
            '[{"base":"anguished"}, {"base":"sad_face"}, {"base":"clap"}]'
        # sample response: https://api.slack.com/methods/emoji.list
        slack_response = AsyncSlackResponse(**{**self.http_args, **{"data": {
            "emoji": {
                "longcat": "some url",
                "doge": "alias",
                "partyparrot": "some url",
            },
            "categories": [ {
                    "name": "faces",
                    "emoji_names": ["smile", "wink"]
                }, {
                    "name": "flags",
                    "emoji_names": ["flag1", "flag2", "flag3"]
                }
            ]
        }}})
        self.client.emoji_list.return_value = slack_response

        # test standard emojis response ok
        emojis = await EmojiOperator._get_reactions_in_team(client=self.client, logger=self.logger)
        self.client.emoji_list.assert_awaited_once_with(include_categories=True)
        # session.get.assert_called_once_with("https://www.emojidex.com/api/v1/utf_emoji")
        mock_context_manager.text.assert_awaited_once_with(encoding="utf-8")
        self.assertSetEqual(set(emojis),
                            set(["longcat", "doge", "partyparrot", "smile", "wink", "flag1", "flag2", "flag3",
                                 "anguished", "sad_face", "clap"]),
                            msg="Could not parse all emojis")

        mock_context_manager.reset_mock()
        get.reset_mock()

        # test standard emojis response not ok
        get.return_value.__aenter__.return_value.status = 500
        emojis = await EmojiOperator._get_reactions_in_team(client=self.client, logger=self.logger)
        mock_context_manager.text.assert_not_awaited()
        self.assertSetEqual(set(emojis),
                            set(["longcat", "doge", "partyparrot", "smile", "wink", "flag1", "flag2", "flag3"]),
                            msg="Should not return standard emojis when invalid http request")

        mock_context_manager.reset_mock()
        get.reset_mock()

        # test standard emojis response exception
        get.return_value.__aenter__.side_effect = ClientConnectorError(None, Mock())
        emojis = await EmojiOperator._get_reactions_in_team(client=self.client, logger=self.logger)
        mock_context_manager.text.assert_not_awaited()
        self.assertSetEqual(set(emojis),
                            set(["longcat", "doge", "partyparrot", "smile", "wink", "flag1", "flag2", "flag3"]),
                            msg="Should not return standard emojis when connection error")

    @patch("multi_reaction_add.internals.EmojiOperator._get_reactions_in_team")
    @patch("multi_reaction_add.internals.datetime")
    async def test_get_valid_reactions(self, datetime_mock: Mock, get_reactions: AsyncMock):
        """Test get_valid_reactions method"""
        EmojiOperator._all_emojis = ["smile", "wink", "face", "laugh", "some-emoji", "-emj-", "_emj_", "some_emoji",
                                      "+one", "'quote'", "54"]
        now_date = datetime.now()
        datetime_mock.now.return_value = now_date

        # check empty input
        emojis = await EmojiOperator.get_valid_reactions(text="", client=self.client, logger=self.logger)
        self.assertListEqual(emojis, [])

        # check no emojis in input
        emojis = await EmojiOperator.get_valid_reactions(text="some text", client=self.client, logger=self.logger)
        self.assertListEqual(emojis, [])

        # check no valid emojis
        emojis = await EmojiOperator.get_valid_reactions(text="::::", client=self.client, logger=self.logger)
        self.assertListEqual(emojis, [])

        # check valid input
        emojis = await EmojiOperator.get_valid_reactions(text=":smile: :wink:", client=self.client, logger=self.logger)
        self.assertListEqual(emojis, ["smile", "wink"])

        # check emojis special characters
        emojis = await EmojiOperator.get_valid_reactions(
            text=":some-emoji: :-emj-: :_emj_: :some_emoji: :+one: :'quote': :54:",
            client=self.client,
            logger=self.logger)
        self.assertListEqual(emojis, ["some-emoji", "-emj-", "_emj_", "some_emoji", "+one", "'quote'", "54"])

        # check remove duplicates
        emojis = await EmojiOperator.get_valid_reactions(
            text=":smile: :wink: :smile:",
            client=self.client,
            logger=self.logger)
        self.assertListEqual(emojis, ["smile", "wink"])

        # check emoji with modifier
        emojis = await EmojiOperator.get_valid_reactions(
            text=":face::skin-tone-2:",
            client=self.client,
            logger=self.logger)
        self.assertListEqual(emojis, ["face::skin-tone-2"])

        # check no space in input
        emojis = await EmojiOperator.get_valid_reactions(
            text=":smile::wink::face::skin-tone-2::face::skin-tone-3::laugh:",
            client=self.client,
            logger=self.logger)
        self.assertListEqual(emojis, ["smile", "wink", "face::skin-tone-2", "face::skin-tone-3", "laugh"])

        # check text and emojis
        emojis = await EmojiOperator.get_valid_reactions(
            text="sometext:smile:anothertext:wink:moretext:laugh:endoftext",
            client=self.client,
            logger=self.logger)
        self.assertListEqual(emojis, ["smile", "wink", "laugh"])

        # check invalid emoji
        emojis = await EmojiOperator.get_valid_reactions(
            text=":smile: :invalid:",
            client=self.client,
            logger=self.logger)
        self.assertListEqual(emojis, ["smile"])

        # check cache is updated when is empty
        EmojiOperator._all_emojis = []
        datetime_mock.reset_mock()
        get_reactions.return_value = ["joy"]
        emojis = await EmojiOperator.get_valid_reactions(text=":joy:", client=self.client, logger=self.logger)
        get_reactions.assert_awaited_once_with(self.client, self.logger)
        datetime_mock.now.assert_called_once()
        self.assertListEqual(emojis, ["joy"])
        self.assertListEqual(EmojiOperator._all_emojis, ["joy"])

        # check cache is updated when is expired
        EmojiOperator._all_emojis = ["123"]
        get_reactions.reset_mock()
        get_reactions.return_value = ["joy"]
        now_date = datetime.now() + timedelta(minutes=2)
        datetime_mock.reset_mock()
        datetime_mock.now.return_value = now_date
        emojis = await EmojiOperator.get_valid_reactions(text=":joy:", client=self.client, logger=self.logger)
        get_reactions.assert_awaited_once_with(self.client, self.logger)
        datetime_mock.now.assert_has_calls([call()] * 2)
        self.assertListEqual(emojis, ["joy"])
        self.assertListEqual(EmojiOperator._all_emojis, ["joy"])
