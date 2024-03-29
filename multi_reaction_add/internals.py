# -*- coding: utf-8 -*-
"""This module contains helper methods called by the handlers.py module."""

import os
import re
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, TextIO
from collections import OrderedDict
from aiohttp import ClientSession, ClientConnectorError, ClientResponseError

from slack_sdk.web.async_client import AsyncWebClient
from google.cloud.storage.bucket import Bucket
from pythonjsonlogger import jsonlogger


class EmojiOperator:
    """Handles emojis validations and updates, and has an in-memory cache for them.

    Attributes:
        _all_emojis (List[str]): a list of all valid emoji codes
        _last_updated (datetime): when was `all_emojis` last updated
    """
    _all_emojis: List[str] = []
    _last_updated = datetime.now()

    @staticmethod
    async def get_user_reactions(client: AsyncWebClient, channel_id: str, message_ts: str, user_id: str) -> List[str]:
        """Gets reactions made by current user to an item.

        The item can be a file, file comment, channel message, group message, or direct message.

        Args:
            client (AsyncWebClient): an initialzied slack web client to communicate with slack API
            channel_id (str): channel id of the item/message
            message_ts (str): timestamp of the item/message
            user_id (str): user id to filter out reactions

        Returns:
            list: list of str with reactions made by the user. otherwise an empty list
        """
        response = await client.reactions_get(channel=channel_id,
                                              timestamp=message_ts)  # gets all reactions on a message
        # handle all possible response types: https://api.slack.com/methods/reactions.get
        if response["type"] == "message":
            if "reactions" in response["message"]:
                return [r["name"] for r in response["message"]["reactions"] if user_id in r["users"]]

        elif response["type"] == "file":
            if "reactions" in response["file"]:
                return [r["name"] for r in response["file"]["reactions"] if user_id in r["users"]]

        elif response["type"] == "file_comment":
            if "reactions" in response["comment"]:
                return [r["name"] for r in response["comment"]["reactions"] if user_id in r["users"]]

        return []

    @staticmethod
    async def _get_reactions_in_team(client: AsyncWebClient, logger: logging.Logger) -> List[str]:
        """Gets the custom + standard emojis available in a Slack workspace, and community emojis too.

        It returns the basic community emojis from emojidex.com because they are not included in the
        Slack API response.

        Args:
            client (AsyncWebClient): an initialized slack WebClient for API calls
            logger (Logger): a logger to print information

        Returns:
            list: list of strings with all emojis
        """
        response = await client.emoji_list(include_categories=True)
        custom_emojis = list(response["emoji"].keys())
        builtin_emojis = [emj for cat in response["categories"]
                        for emj in cat["emoji_names"]]
        standard_emojis = []
        async with ClientSession() as session:
            try:
                async with session.get('https://www.emojidex.com/api/v1/utf_emoji') as resp:
                    if resp.status == 200:
                        json_text = await resp.text(encoding='utf-8')
                        standard_emojis = json.loads(json_text)
                        standard_emojis = [e["base"] for e in standard_emojis]
                    else:
                        logger.warning(
                            "Could not retrieve standard emojis: %s %s", resp.status, resp.reason)

            except (ClientConnectorError, ClientResponseError):
                logger.exception("Failed to get standard emojis")

        return list(set(custom_emojis + builtin_emojis + standard_emojis))

    @staticmethod
    async def get_valid_reactions(
        text: str,
        client: AsyncWebClient,
        logger: logging.Logger) -> List[str]:
        """Returns the valid emojis available in user's workspace, if any.

        Args:
            text (str): message from the user which contains possible emojis
            client (AsyncWebClient): an initialized slack WebClient for API calls
            logger (Logger): a logger to print information

        Returns:
            list: a list of strings containing valid emojis from user
        """
        # find all :emoji: and :thumbsup::skin-tone-2: strings
        reactions = re.findall(r":[a-z0-9-_\+']+(?:::skin\-tone\-\d+)?:", text)
        # remove duplicates and keep original positions
        reactions = list(dict.fromkeys(reactions))
        if not reactions:
            return []

        reactions = [r[1:-1] for r in reactions]  # strip the colons
        orig_reactions = reactions.copy()  # keep list wth original positions
        simple_reactions = []  # holds simple reactions. e.g. thumbsup
        reactions_with_modifier = []  # holds reactions with modifiers. e.g. thumbsup::skin-tone-2
        for reaction in reactions:
            if "::" in reaction:
                reactions_with_modifier.append(reaction)
            else:
                simple_reactions.append(reaction)

        # update cache when is empty or older than 1min
        if not EmojiOperator._all_emojis or (EmojiOperator._last_updated < datetime.now() - timedelta(minutes=1)):
            EmojiOperator._all_emojis = await EmojiOperator._get_reactions_in_team(client, logger)
            EmojiOperator._last_updated = datetime.now()

        valid_reactions = [r for r in simple_reactions if r in EmojiOperator._all_emojis]
        valid_reactions += [
            r for r in reactions_with_modifier if r[:r.find("::")] in EmojiOperator._all_emojis]
        # return reactions back in order
        return [r for r in orig_reactions if r in valid_reactions]


async def delete_users_data(
    bucket: Bucket,
    slack_client_id: str,
    enterprise_id: Optional[str],
    team_id: str,
    user_ids: List[str]) -> None:
    """Delete user data emojis for all input user ids.

    Args:
        bucket (Bucket): GCS bucket containing user data
        slack_client_id (str): Slack application client id
        enterprise_id (Optional[str]): Slack enterprise id or None
        team_id (str): Slack team id
        user_ids (List[str]): Slack user ids
    """
    for user_id in user_ids:
        blob = bucket.blob(user_data_key(slack_client_id=slack_client_id,
                                         enterprise_id=enterprise_id,
                                         team_id=team_id,
                                         user_id=user_id
                                         ))
        if blob.exists():
            blob.delete()


def user_data_key(slack_client_id: str, enterprise_id: Optional[str], team_id: str, user_id: str) -> str:
    """Return the location for user data (emojis) in the google bucket.

    Args:
        slack_client_id (str): Slack application client id
        enterprise_id (Optional[str]): Slack enterprise id or None
        team_id (str): Slack team id
        user_id (str): Slack user id

    Returns:
        str: location in the GCS bucket for the user data
    """
    return (f"{slack_client_id}/{enterprise_id}-{team_id}/{user_id}"
            if enterprise_id
            else
            f"{slack_client_id}/none-{team_id}/{user_id}")


def build_home_tab_view(slash_command: str, app_url: str = None) -> dict:
    """Builds a Slack Block Kit view for the App Home Tab.

    Args:
        slash_command (str): Slack slash command the app responds to.
        app_url (str): Application URL to add additional pictures in the view. Defaults to None.

    Returns:
        dict: a block kit user interface of type "home"
    """
    blocks = []
    view = {"type": "home", "blocks": blocks}
    blocks.extend([
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Setting emojis :floppy_disk:",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Type `{slash_command} <list of emojis>` in any chat to set a list of emojis for later usage."
            }
        }
    ])
    if app_url:
        blocks.extend([
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-write-emojis.png?w=1024&ssl=1",
                "alt_text": "write emojis"
            },
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-save.png?w=1024&ssl=1",
                "alt_text": "saved emojis"
            }
        ])

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"You can view what you saved any moment by typing `{slash_command}` in any chat."
        }
    })
    if app_url:
        blocks.extend([
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-write-nothing.png?w=1024&ssl=1",
                "alt_text": "view emojis"
            },
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-view.png?w=1024&ssl=1",
                "alt_text": "view emojis"
            }
        ])

    blocks.extend([
        {
            "type": "divider"
        },
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Adding Reactions :star-struck:",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ("Go to a message, click `More Actions`, then click on `Multireact` to react with the saved "
                         "emojis to the message.\n\nIf you can't see `Multireact`, click `More message shortcuts...` "
                         "to find it.")
            }
        }
    ])
    if app_url:
        blocks.extend([
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-none.png?w=1024&ssl=1",
                "alt_text": "message with no reactions"
            },
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-menu.png?w=1024&ssl=1",
                "alt_text": "message menu"
            },
            {
                "type": "image",
                "image_url": f"{app_url}/img/reaction-add.png?w=1024&ssl=1",
                "alt_text": "message with reactions"
            }
        ])

    return view


def check_env() -> None:
    """Checks if mandatory environment variables are set.

    Raises:
        RuntimeError: when one or more environment variables are missing
    """
    keys = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET", "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME",
            "SLACK_STATE_GOOGLE_BUCKET_NAME", "USER_DATA_BUCKET_NAME"]
    missing = [key for key in keys if key not in os.environ]
    if missing:
        raise RuntimeError(f"The following environment variables are not set: {missing}")


def setup_logger(stream: TextIO = sys.stderr) -> logging.Logger:
    """Changes python root logger to a json based one that's compatible with Cloud Run logs.

    Args:
        stream (TextIO): a text stream where to write the logs. Defaults to sys.stderr

    Returns:
        logging.Logger: a reference to the root logger.
    """
    logger = logging.getLogger()
    logger.setLevel(os.environ.get("UVICORN_LOG_LEVEL", "info").upper())
    log_handler = logging.StreamHandler(stream)
    formatter = CloudLoggingJsonFormatter("%(timestamp)s %(severity)s %(funcName)s %(component)s %(message)s")
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)
    return logger


class CloudLoggingJsonFormatter(jsonlogger.JsonFormatter):
    """A json log formatter suitable for Google Cloud Logging reporting.

    Todo:
        * use X-Cloud-Trace-Context to group logs:
        https://cloud.google.com/appengine/docs/standard/python3/writing-application-logs#writing_structured_logs
    """

    def add_fields(self, log_record: OrderedDict, record: logging.LogRecord, message_dict: dict) -> None:
        """Override super.add_fields to add extra fields required for Cloud Logs.

        Args:
            log_record (OrderedDict): Output log fields
            record (logging.LogRecord): Original log entry
            message_dict (dict): Additional information attached to the json log
        """
        super().add_fields(log_record, record, message_dict)
        log_record["severity"] = record.levelname
        log_record["component"] = record.name
        log_record["timestamp"] = self.formatTime(record)
