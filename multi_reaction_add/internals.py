import re


async def _get_reactions_in_team(client):
    """Gets the emojis available in a workspace

    Args:
        client (WebClient): an initialized slack WebClient for API calls

    Returns:
        list: list of strings with all emojis
    """
    response = await client.emoji_list(include_categories=True)

    custom_emojis = list(response["emoji"].keys())
    builtin_emojis = [emj for cat in response["categories"] for emj in cat["emoji_names"]]
    return custom_emojis + builtin_emojis


async def get_valid_reactions(text, client):
    """Returns the valid emojis available in user's workspace, if any

    Args:
        text (str): message from the user which contains possible emojis
        client (WebClient): an initialized slack WebClient for API calls

    Returns:
        list: a list of strings containing valid emojis from user
    """
    # TODO: :thumbsup::skin-tone-2:
    reactions = re.findall(r":[a-z0-9-_\+']+:", text) # find all :emoji: strings
    reactions = list(dict.fromkeys(reactions)) # remove duplicates
    if not reactions:
        return []

    reactions = [r[1:-1] for r in reactions] # strip the colons
    all_reactions = await _get_reactions_in_team(client)
    return [r for r in reactions if r in all_reactions]
