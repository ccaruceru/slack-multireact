import re
import logging
import json
from typing import List
from aiohttp import ClientSession, ClientConnectorError, ClientResponseError
from slack_sdk.web.async_client import AsyncWebClient


async def get_user_reactions(client: AsyncWebClient, channel_id: str, message_ts: str, user_id: str) -> List[str]:
    """Gets reactions made by current user to an item (file, file comment, channel message, group message, or direct message)

    Args:
        client (WebClient): an initialzied slack web client to communicate with slack API
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

        except (ClientConnectorError, ClientResponseError) as e:
            logger.warning(f"Could not retrieve standard emojis: {e}")

    return list(set(custom_emojis + builtin_emojis + standard_emojis))


async def get_valid_reactions(text: str, client: AsyncWebClient, logger: logging.Logger) -> List[str]:
    """Returns the valid emojis available in user's workspace, if any

    Args:
        text (str): message from the user which contains possible emojis
        client (WebClient): an initialized slack WebClient for API calls
        logger (Logger): a logger to print information

    Returns:
        list: a list of strings containing valid emojis from user
    """
    reactions = re.findall(r":[a-z0-9-_\+']+(?:::[a-z0-9-_\+']+){0,1}:", text) # find all :emoji: and :thumbsup::skin-tone-2: strings
    reactions = list(dict.fromkeys(reactions)) # remove duplicates and keep original positions
    if not reactions:
        return []

    reactions = [r[1:-1] for r in reactions] # strip the colons
    orig_reactions = reactions.copy() # keep list wth original positions
    simple_reactions = [] # holds simple reactions. e.g. thumbsup
    reactions_with_modifier = [] # holds reactions with modifiers. e.g. thumbsup::skin-tone-2
    for r in reactions:
        reactions_with_modifier.append(r) if "::" in r else simple_reactions.append(r)

    all_reactions = await _get_reactions_in_team(client, logger)
    valid_reactions =  [r for r in simple_reactions        if r                in all_reactions]
    valid_reactions += [r for r in reactions_with_modifier if r[:r.find("::")] in all_reactions]
    return [r for r in orig_reactions if r in valid_reactions] # return reactions back in order
