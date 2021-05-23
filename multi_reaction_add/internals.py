import os
import re
import asyncio
import logging
import json
from collections import OrderedDict
from typing import List
from aiohttp import ClientSession, ClientConnectorError, ClientResponseError
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from pythonjsonlogger import jsonlogger


# list of all emojis available in this team
ALL_EMOJIS = []


async def get_user_reactions(client: AsyncWebClient, channel_id: str, message_ts: str, user_id: str) -> List[str]:
    """Gets reactions made by current user to an item (file, file comment, channel message, group message, or direct message)

    Args:
        client (WebClient): an initialzied slack web client to communicate with slack API
        channel_id (str): channel id of the item/message
        message_ts (str): timestamp of the item/message
        user_id (str): user id to filter out reactions

    Returns:
        list: list of str with reactions made by the user. otherwise an empty list
    """
    response = await client.reactions_get(channel=channel_id, timestamp=message_ts) # gets all reactions on a message
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


async def _update_emoji_list(app: AsyncApp, token: str, logger: logging.Logger) -> None:
    """Updates the global emojis list with latest from slack api

    Args:
        app (AsyncApp): Bolt application instance
        token (str): bot token to make api calls
        logger (logging.Logger): logger for printing messages
    """
    global ALL_EMOJIS

    while True:
        await asyncio.sleep(60) # 1 min
        try:
            logging.info("Start emoji update")
            old_token = app.client.token
            app.client.token = token
            ALL_EMOJIS = await _get_reactions_in_team(app.client, logger)
            app.client.token = old_token
            logging.info("Emoji update finished")
        except SlackApiError:
            logging.exception("Failed to update emoji list")


async def _get_reactions_in_team(client: AsyncWebClient, logger: logging.Logger) -> List[str]:
    """Gets the custom emojis available in a workspace plus the standard available ones
    https://king.slack.com/help/requests/3477073

    Args:
        client (WebClient): an initialized slack WebClient for API calls
        logger (Logger): a logger to print information

    Returns:
        list: list of strings with all emojis
    """
    response = await client.emoji_list(include_categories=True)
    custom_emojis = list(response["emoji"].keys())
    builtin_emojis = [emj for cat in response["categories"] for emj in cat["emoji_names"]]
    standard_emojis = []
    async with ClientSession() as session:
        try:
            async with session.get('https://www.emojidex.com/api/v1/utf_emoji') as resp:
                if resp.status == 200:
                    json_text = await resp.text(encoding='utf-8')
                    standard_emojis = json.loads(json_text)
                    standard_emojis = [e["base"] for e in standard_emojis]
                else:
                    logger.warning(f"Could not retrieve standard emojis: {resp.status} {resp.reason}")

        except (ClientConnectorError, ClientResponseError):
            logger.exception("Failed to get standard emojis")

    return list(set(custom_emojis + builtin_emojis + standard_emojis))


async def get_valid_reactions(text: str, client: AsyncWebClient, app: AsyncApp, logger: logging.Logger) -> List[str]:
    """Returns the valid emojis available in user's workspace, if any

    Args:
        text (str): message from the user which contains possible emojis
        client (WebClient): an initialized slack WebClient for API calls
        app (AsyncApp): the Bolt application instance
        logger (Logger): a logger to print information

    Returns:
        list: a list of strings containing valid emojis from user
    """
    global ALL_EMOJIS

    reactions = re.findall(r":[a-z0-9-_\+']+(?:::skin\-tone\-\d+)?:", text) # find all :emoji: and :thumbsup::skin-tone-2: strings
    reactions = list(dict.fromkeys(reactions)) # remove duplicates and keep original positions
    if not reactions:
        return []

    reactions = [r[1:-1] for r in reactions] # strip the colons
    orig_reactions = reactions.copy() # keep list wth original positions
    simple_reactions = [] # holds simple reactions. e.g. thumbsup
    reactions_with_modifier = [] # holds reactions with modifiers. e.g. thumbsup::skin-tone-2
    for r in reactions:
        reactions_with_modifier.append(r) if "::" in r else simple_reactions.append(r)

    if not ALL_EMOJIS:
        ALL_EMOJIS = await _get_reactions_in_team(client, logger)
        # start a thread to update all emojis for future use
        asyncio.create_task(coro=_update_emoji_list(app, client.token, logger), name="EmojiUpdate")

    valid_reactions =  [r for r in simple_reactions        if r                in ALL_EMOJIS]
    valid_reactions += [r for r in reactions_with_modifier if r[:r.find("::")] in ALL_EMOJIS]
    return [r for r in orig_reactions if r in valid_reactions] # return reactions back in order


def build_home_tab_view(app_url: str = None) -> dict:
    """Builds a Slack Block Kit view for the App Home Tab

    Args:
        app_url (str, optional): Application URL to add additional pictures in the view. Defaults to None.

    Returns:
        dict: a block kit user interface of type "home"
    """
    blocks = []
    view = {"type": "home", "blocks": blocks }
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
                "text": "Type `/multireact <list of emojis>` in any chat to set a list of emojis for later usage."
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
            "text": "You can view what you saved any moment by typing `/multireact` in any chat."
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
                "text": "Go to a message, click `More Actions`, then click on `Multireact` to react with the saved emojis to the message.\n\nIf you can't see `Multireact`, click `More message shortcuts...` to find it."
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


def setup_logger() -> None:
    """Changes python logger to a json based one that's compatible with Cloud Run logs
    """
    logger = logging.getLogger()
    logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
    logHandler = logging.StreamHandler()
    formatter = CloudRunJsonFormatter('%(timestamp)s %(severity)s %(funcName)s %(component)s %(message)s')
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)


class CloudRunJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record: OrderedDict, record: logging.LogRecord, message_dict: dict) -> None:
        """Override the super.add_fields to add an extra levelname required for Cloud logs

        Args:
            log_record (OrderedDict): Output log fields
            record (logging.LogRecord): Original log entry
            message_dict (dict): Additional information attached to the json log
        """
        super().add_fields(log_record, record, message_dict)
        log_record['severity']  = record.levelname
        log_record['component'] = record.name
        log_record['timestamp'] = self.formatTime(record)
