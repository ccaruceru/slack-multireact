import re
from typing import List
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


async def _get_reactions_in_team(client: AsyncWebClient) -> List[str]:
    """Gets the emojis available in a workspace

    Args:
        client (WebClient): an initialized slack WebClient for API calls

    Returns:
        list: list of strings with all emojis
    """
    response = await client.emoji_list(include_categories=True)
    custom_emojis = list(response["emoji"].keys())
    builtin_emojis = [emj for cat in response["categories"] for emj in cat["emoji_names"]]
    # TODO: handle thumbsup: https://king.slack.com/help/requests/3477073
    return custom_emojis + builtin_emojis


async def get_valid_reactions(text: str, client: AsyncWebClient) -> List[str]:
    """Returns the valid emojis available in user's workspace, if any

    Args:
        text (str): message from the user which contains possible emojis
        client (WebClient): an initialized slack WebClient for API calls

    Returns:
        list: a list of strings containing valid emojis from user
    """
    reactions = re.findall(r":[a-z0-9-_\+']+(?:::[a-z0-9-_\+']+){0,1}:", text) # find all :emoji: and :thumbsup::skin-tone-2: strings
    reactions = list(dict.fromkeys(reactions)) # remove duplicates
    if not reactions:
        return []

    reactions = [r[1:-1] for r in reactions] # strip the colons
    simple_reactions = [] # holds simple reactions. e.g. thumbsup
    reactions_with_modifier = [] # holds reactions with modifiers. e.g. thumbsup::skin-tone-2
    for r in reactions:
        reactions_with_modifier.append(r) if "::" in r else simple_reactions.append(r)

    all_reactions = await _get_reactions_in_team(client)
    valid_reactions =  [r for r in simple_reactions        if r                in all_reactions]
    valid_reactions += [r for r in reactions_with_modifier if r[:r.find("::")] in all_reactions]
    return valid_reactions
