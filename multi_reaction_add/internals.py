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
    # TODO: handle thumbsup: https://king.slack.com/help/requests/3477073
    return custom_emojis + builtin_emojis


async def get_valid_reactions(text, client):
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
