import logging
import os
import re
import threading
from pathlib import Path
from time import sleep

from slack_bolt import App
from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_sdk.errors import SlackApiError
from multi_reaction_add.oauth.installation_store.google_cloud_storage import GoogleCloudStorageInstallationStore
from multi_reaction_add.oauth.state_store.google_cloud_storage import GoogleCloudStorageOAuthStateStore
from slack_bolt.adapter.flask import SlackRequestHandler # https://slack.dev/bolt-python/concepts#adapters

from google.cloud.storage import Client


logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))

TIER2_LIMIT_SEC = (20-2)/60 # Slack tier 2 api rate limit: 20/min
TIER3_LIMIT_SEC = (50-5)/60 # Slack tier 3 api rate limit: 50/min
TIER4_LIMIT_SEC = 110/60 # Slack tier 4 api rate limit: 100+/min

# initialize the Google Storage client
storage_client = Client()
BUCKET = storage_client.bucket(os.environ["USER_DATA_BUCKET_NAME"])

# Initialize the app with the OAuth configuration
# TODO: asyncio app
app = App(
    process_before_response=("LOCAL_DEVELOPMENT" not in os.environ), # process_before_response must be True when running on FaaS
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    oauth_settings=OAuthSettings(
        client_id=os.environ["SLACK_CLIENT_ID"],
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=["commands", "emoji:read"], # scopes needed for bot operations
        user_scopes=["reactions:write"], # scopes needed for operations on behalf of user
        installation_store=GoogleCloudStorageInstallationStore(
            storage_client=storage_client,
            bucket_name=os.environ["SLACK_INSTALLATION_GOOGLE_BUCKET_NAME"],
            client_id=os.environ["SLACK_CLIENT_ID"]
        ),
        state_store=GoogleCloudStorageOAuthStateStore(
            storage_client=storage_client,
            bucket_name=os.environ["SLACK_STATE_GOOGLE_BUCKET_NAME"],
            expiration_seconds=600
        )
    )
)
# Google fucntions are using Flask https://github.com/slackapi/bolt-python/pull/45
handler = SlackRequestHandler(app)


def _get_reactions_in_team(client):
    """Gets the emojis available in a workspace

    Args:
        client (WebClient): an initialized slack WebClient for API calls

    Returns:
        list: list of strings with all emojis
    """
    try:
        response = client.emoji_list(include_categories=True)
    finally:
        sleep(TIER2_LIMIT_SEC)

    custom_emojis = list(response["emoji"].keys())
    builtin_emojis = [emj for cat in response["categories"] for emj in cat["emoji_names"]]
    return custom_emojis + builtin_emojis


def _get_valid_reactions(text, client):
    """Returns the valid emojis available in user's workspace, if any

    Args:
        text (str): message from the user which contains possible emojis
        client (WebClient): an initialized slack WebClient for API calls

    Returns:
        list: a list of strings containing valid emojis from user
    """
    reactions = re.findall(r":[a-z0-9-_\+']+:", text) # find all :emoji: strings
    reactions = list(dict.fromkeys(reactions)) # remove duplicates
    if not reactions:
        return []

    reactions = [r[1:-1] for r in reactions] # strip the colons
    return [r for r in reactions if r in _get_reactions_in_team(client)]


def _get_rendered_reactions(reactions):
    """Returns a UI friendly list of reactions for Slack

    Args:
        reactions (str): raw reactions read from disk

    Returns:
        str: reactions that can be rendered in UI
    """
    return " ".join([f":{r}:" for r in reactions.split(" ")])


@app.command("/multireact") # https://api.slack.com/interactivity/slash-commands, https://slack.dev/bolt-python/concepts#commands 
def save_or_display_reactions(ack, client, command, respond, logger):
    # TODO: move methods contents to dedicated file in package
    """Handler for slack command:
      "/multireact"      - display reactions for curent user, or inform that none is set
      "/multireact text" - set reactions for current user

    Args:
        ack (Ack): function to inform slack that an event has been received
        client (WebClient): an initialzied slack web client to communicate with slack API
        command (str): json payload with information about the command triggered by the user
        respond (Respond): function that sends an ephemeral response for slack commands
        logger (Logger): optional logger passed to all handlers

    Raises:
         SlackApiError: whenever Slack api calls fail
         IOError: whenever user data cannot be read or saved
         OSError: whenever user data cannot be read or saved
    """
    ack() # commands must be acknowledged with ack() to inform Slack your app has received the event.
    # sample command
    # {'token': 'MKxqqxT4PQMBnyNJdjAocKOF', 'team_id': 'T01S9QDF7AT', 'team_domain': 'ccc-yzo4468', 'channel_id': 'D01T36EUQTT', 'channel_name': 'directmessage', 'user_id': 'U01SWNKJR6G', 'user_name': 'user.name', 'command': '/multireact', 'text': ':+1::raised_hands::eyes::clap::large_blue_circle::100::heart:', 'api_app_id': 'A01S9QL1VAT', 'is_enterprise_install': 'false', 'response_url': 'https://hooks.slack.com/commands/T01S9QDF7AT/1910458772038/JZenAWWRrsPnTqV8QtqZ5Un0', 'trigger_id': '1917238991026.1893829517367.a413f69683ea053e0791c739a29a6da4'}
    user_id = command["user_id"]
    blob = BUCKET.blob(user_id)

    if "text" in command: # this command has some text in it => will save new reactions
        reactions = _get_valid_reactions(command["text"], client) # sanitize the mesage from user and select only reactions
        # sleep was handled in _get_valid_reactions
        if len(reactions) > 23: # inform user when reaction limit reached: https://slack.com/intl/en-se/help/articles/206870317-Use-emoji-reactions
            respond(("Slow down! You tried to save more than 23 reactions :racing_car:\nTry using less reactions this time :checkered_flag:"))
            logger.info(f"User {user_id} tried to add >23 reactions")

        elif len(reactions) == 0: # no reactions found in the given text
            respond(("Oh no! You did not provide any valid reactions :open_mouth:\nMake sure you type the reactions starting with `:`,"
                    " or use the Emoji button (:slightly_smiling_face:) to add one."))
            logger.info(f"User {user_id} set no valid reactions")

        else: # valid reactions were given to be saved
            reactions = " ".join(reactions)
            blob.upload_from_string(reactions)
            respond("Great! Your new reactions are saved :sunglasses: Type `/multireact` to see them at any time.")
            logger.info(f"User {user_id} saved {reactions}")

    else: # otherwise, report to user any reactions they have
        if blob.exists(): # display any reactions the user has saved
            reactions = blob.download_as_text(encoding="utf-8")
            try:
                respond(f"Your current reactions are: {_get_rendered_reactions(reactions)}. Type `/multireact <new list of emojis>` to change them.")
                logger.info(f"User {user_id} loaded {reactions}")
            finally:
                sleep(TIER4_LIMIT_SEC)

        else: # or say that user doesn't have any
            try:
                respond("You do not have any reactions set :anguished:\nType `/multireact <list of emojis>` to set one.")
                logger.info(f"User {user_id} has no reactions")
            finally:
                sleep(TIER4_LIMIT_SEC)


@app.shortcut("add_reactions")
def add_reactions(ack, shortcut, client, logger, context):
    """Handler for message shortcut functionality where the user adds the recorded reactions to the message mentioned in the shortcut activity

    Args:
        ack (Ack): function to inform slack that an event has been received
        shortcut (str): json payload with information about the shortcut triggered by the user
        client (WebClient): an initialzied slack web client to communicate with slack API
        logger (Logger): optional logger passed to all handlers
        context (BoltContext): a dictionary added to all handlers which can be used to enrich events with additional information

    Raises:
         SlackApiError: whenever Slack api calls fail
         IOError: whenever user data cannot be read or saved
         OSError: whenever user data cannot be read or saved
    """
    ack() # commands must be acknowledged with ack() to inform Slack your app has received the event.
    # sample shortcut
    # {'type': 'message_action', 'token': 'MKxqqxT4PQMBnyNJdjAocKOF', 'action_ts': '1617307130.812650', 'team': {'id': 'T01S9QDF7AT', 'domain': 'ccc-yzo4468'}, 'user': {'id': 'U01SWNKJR6G', 'username': 'user.name', 'team_id': 'T01S9QDF7AT', 'name': 'User Name'}, 'channel': {'id': 'C01S9QDFYNT', 'name': 'general'}, 'is_enterprise_install': False, 'enterprise': None, 'callback_id': 'add_reactions', 'trigger_id': '1921893944962.1893829517367.a00ca10cfbff650e5eda3e6a446fbc18', 'response_url': 'https://hooks.slack.com/app/T01S9QDF7AT/1918813724821/CTVMTDtdahKL9Vdrbee00sZG', 'message_ts': '1617307089.003400', 'message': {'client_msg_id': '6f9e6469-14ed-4bf8-8dee-7170b17af92b', 'type': 'message', 'text': 'asdfghjkl', 'user': 'U01SWNKJR6G', 'ts': '1617307089.003400', 'team': 'T01S9QDF7AT', 'blocks': [{'type': 'rich_text', 'block_id': 'm3V', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'text', 'text': 'asdfghjkl'}]}]}]}}
    user_id = shortcut["user"]["id"]
    message_ts = shortcut["message_ts"]
    channel_id = shortcut["channel"]["id"]
    blob = BUCKET.blob(user_id)
    reactions = None
    if blob.exists():
        reactions = blob.download_as_text(encoding="utf-8")

    if reactions: # if user has any reactions saved, add them to the message
        for reaction in reactions.split(" "): # saved as a whitespace separated string
            try:
                client.token = context.user_token # alter context to post on users's behalf: https://slack.dev/java-slack-sdk/guides/bolt-basics#use-web-apis--reply-using-say-utility
                try:
                    # TODO: read reactions first, do a diff and react with the remaining emojis
                    client.reactions_add(
                        channel=channel_id,
                        timestamp=message_ts,
                        name=reaction
                    )
                    logger.info(f"User {user_id} reacted {reaction} on message {message_ts} from channel {channel_id}")
                finally:
                    sleep(TIER3_LIMIT_SEC)

            except SlackApiError as err: # if the error message says the user already reacted then ignore it
                if not ("error" in err.response.data and err.response.data["error"] == "already_reacted"):
                    raise err

    else: # if user set no reactions, display a dialogue to inform the user that no reactions are set
        try:
            client.views_open(
                trigger_id=shortcut["trigger_id"],
                view={
                    "type": "modal",
                    "title": {
                        "type": "plain_text",
                        "text": "Multi Reaction Add"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "Close"
                    },
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "You do not have any reactions set :anguished:\nType `/multireact <list of emojis>` in the chat to set one."
                            }
                        }
                    ]
                }
            )
            logger.info(f"User {user_id} has no reactions")
        finally:
            sleep(TIER4_LIMIT_SEC)


# TODO: handle token revoked and app uninstalled events: https://gist.github.com/seratch/d81a445ef4467b16f047156bf859cda8#file-main-py-L50-L65
# TODO: save user data the same way oauth does: with workspace_id, enterprise_id and team_id
# TODO: update docs
