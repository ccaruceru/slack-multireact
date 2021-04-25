import os
from slack_bolt.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_sdk.errors import SlackApiError
from slack_sdk.web import SlackResponse
from multi_reaction_add.oauth.installation_store.google_cloud_storage import GoogleCloudStorageInstallationStore
from multi_reaction_add.oauth.state_store.google_cloud_storage import GoogleCloudStorageOAuthStateStore
from multi_reaction_add.internals import get_valid_reactions
from google.cloud.storage import Client


# initialize the Google Storage client
storage_client = Client()
bucket = storage_client.bucket(os.environ["USER_DATA_BUCKET_NAME"])
slack_client_id = os.environ["SLACK_CLIENT_ID"]
# Initialize the app with the OAuth configuration
app = AsyncApp(
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    oauth_settings=AsyncOAuthSettings(
        client_id=slack_client_id,
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=["commands", "emoji:read"], # scopes needed for bot operations
        user_scopes=["reactions:write"], # scopes needed for operations on behalf of user
        installation_store=GoogleCloudStorageInstallationStore(
            storage_client=storage_client,
            bucket_name=os.environ["SLACK_INSTALLATION_GOOGLE_BUCKET_NAME"],
            client_id=slack_client_id
        ),
        state_store=GoogleCloudStorageOAuthStateStore(
            storage_client=storage_client,
            bucket_name=os.environ["SLACK_STATE_GOOGLE_BUCKET_NAME"],
            expiration_seconds=600
        )
    )
)


@app.command("/multireact") # https://api.slack.com/interactivity/slash-commands, https://slack.dev/bolt-python/concepts#commands 
async def save_or_display_reactions(ack, client, command, respond, logger):
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
    await ack() # commands must be acknowledged with ack() to inform Slack your app has received the event.
    # sample commands
    # {'token': 'MKxqqxT4PQMBnyNJdjAocKOF', 'team_id': 'T01S9QDF7AT', 'team_domain': 'ccc-yzo4468', 'channel_id': 'D01T36EUQTT', 'channel_name': 'directmessage', 'user_id': 'U01SWNKJR6G', 'user_name': 'user.name', 'command': '/multireact', 'text': ':+1::raised_hands::eyes::clap::large_blue_circle::100::heart:', 'api_app_id': 'A01S9QL1VAT', 'is_enterprise_install': 'false', 'response_url': 'https://hooks.slack...WRrsPnTqV8QtqZ5Un0', 'trigger_id': '1917238991...9a29a6da4'}
    # or
    # {'api_app_id': 'A01TWV8NAEN', 'channel_id': 'D01SQA99362', 'channel_name': 'directmessage', 'command': '/multireact', 'enterprise_id': 'EG26V10SE', 'enterprise_name': 'ABK-SB', 'is_enterprise_install': 'false', 'response_url': 'https://hooks.slack....UFIRvQgGs0', 'team_domain': 'kingcom-sandbox', 'team_id': 'T8T3GKUKZ', 'token': 'wF8MDfFS8BLd30KFYLT1MlZa', 'trigger_id': '1995489393941.299118...b1d2b8f830', 'user_id': 'U01SXA059B5', 'user_name': 'cristian.caruceru'}
    user_id = command["user_id"]
    team_id = command["team_id"]
    enterprise_id = "none"
    if "enterprise_id" in command:
        enterprise_id = command["enterprise_id"]

    blob = bucket.blob(f"{slack_client_id}/{enterprise_id}-{team_id}/{user_id}")

    if "text" in command: # this command has some text in it => will save new reactions
        reactions = await get_valid_reactions(command["text"], client) # sanitize the mesage from user and select only reactions
        if len(reactions) > 23: # inform user when reaction limit reached: https://slack.com/intl/en-se/help/articles/206870317-Use-emoji-reactions
            await respond(("Slow down! You tried to save more than 23 reactions :racing_car:\nTry using less reactions this time :checkered_flag:"))
            logger.info(f"User {user_id} tried to add >23 reactions")

        elif len(reactions) == 0: # no reactions found in the given text
            await respond(("Oh no! You did not provide any valid reactions :open_mouth:\nMake sure you type the reactions starting with `:`,"
                    " or use the Emoji button (:slightly_smiling_face:) to add one."))
            logger.info(f"User {user_id} set no valid reactions")

        else: # valid reactions were given to be saved
            reactions = " ".join(reactions)
            blob.upload_from_string(reactions)
            await respond("Great! Your new reactions are saved :sunglasses: Type `/multireact` to see them at any time.")
            logger.info(f"User {user_id} saved {reactions}")

    else: # otherwise, report to user any reactions they have
        if blob.exists(): # display any reactions the user has saved
            reactions = blob.download_as_text(encoding="utf-8")
            reactions = " ".join([f":{r}:" for r in reactions.split(" ")])
            await respond(f"Your current reactions are: {reactions}. Type `/multireact <new list of emojis>` to change them.")
            logger.info(f"User {user_id} loaded {reactions}")

        else: # or say that user doesn't have any
            await respond("You do not have any reactions set :anguished:\nType `/multireact <list of emojis>` to set one.")
            logger.info(f"User {user_id} has no reactions")


@app.shortcut("add_reactions")
async def add_reactions(ack, shortcut, client, logger, context):
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
    await ack() # commands must be acknowledged with ack() to inform Slack your app has received the event.
    # sample shortcut
    # {'type': 'message_action', 'token': 'MKxqqxT4PQMBnyNJdjAocKOF', 'action_ts': '1617307130.812650', 'team': {'id': 'T01S9QDF7AT', 'domain': 'ccc-yzo4468'}, 'user': {'id': 'U01SWNKJR6G', 'username': 'user.name', 'team_id': 'T01S9QDF7AT', 'name': 'User Name'}, 'channel': {'id': 'C01S9QDFYNT', 'name': 'general'}, 'is_enterprise_install': False, 'enterprise': None, 'callback_id': 'add_reactions', 'trigger_id': '1921893944...3e6a446fbc18', 'response_url': 'https://hooks.slack...L9Vdrbee00sZG', 'message_ts': '1617307089.003400', 'message': {'client_msg_id': '6f9e6469-1...70b17af92b', 'type': 'message', 'text': 'asdfghjkl', 'user': 'U01SWNKJR6G', 'ts': '1617307089.003400', 'team': 'T01S9QDF7AT', 'blocks': [{'type': 'rich_text', 'block_id': 'm3V', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'text', 'text': 'asdfghjkl'}]}]}]}}
    # or
    # {'action_ts': '1619339417.302061', 'callback_id': 'add_reactions', 'channel': {'id': 'C01V7KXNRRS', 'name': 'slapp-1119'}, 'enterprise': {'id': 'EG26V10SE', 'name': 'ABK-SB'}, 'is_enterprise_install': False, 'message': {'blocks': [...], 'client_msg_id': '437b2675-6524-4724-a...69a4e0b9f6', 'team': 'T8T3GKUKZ', 'text': '210', 'ts': '1619339414.000200', 'type': 'message', 'user': 'U01SXA059B5'}, 'message_ts': '1619339414.000200', 'response_url': 'https://hooks.slack....tkt5yMCogg', 'team': {'domain': 'kingcom-sandbox', 'enterprise_id': 'EG26V10SE', 'enterprise_name': 'ABK-SB', 'id': 'T8T3GKUKZ'}, 'token': 'wF8MDfFS8BLd30KFYLT1MlZa', 'trigger_id': '1991796659910.299118...7619ad8bd4', 'type': 'message_action', 'user': {'id': 'U01SXA059B5', 'name': 'cristian.caruceru', 'team_id': 'T8T3GKUKZ', 'username': 'cristian.caruceru'}}
    user_id = shortcut["user"]["id"]
    team_id = shortcut["team"]["id"]
    enterprise_id = "none"
    if shortcut["enterprise"]:
        enterprise_id = shortcut["enterprise"]["id"]

    message_ts = shortcut["message_ts"]
    channel_id = shortcut["channel"]["id"]
    blob = bucket.blob(f"{slack_client_id}/{enterprise_id}-{team_id}/{user_id}")
    reactions = None
    if blob.exists():
        reactions = blob.download_as_text(encoding="utf-8")

    if reactions: # if user has any reactions saved, add them to the message
        for reaction in reactions.split(" "): # saved as a whitespace separated string
            try:
                client.token = context.user_token # alter context to post on users's behalf: https://slack.dev/java-slack-sdk/guides/bolt-basics#use-web-apis--reply-using-say-utility
                # TODO: read reactions first, do a diff and react with the remaining emojis
                await client.reactions_add(
                    channel=channel_id,
                    timestamp=message_ts,
                    name=reaction
                )
                logger.info(f"User {user_id} reacted {reaction} on message {message_ts} from channel {channel_id}")

            except SlackApiError as err: # if the error message says the user already reacted then ignore it
                # TODO: slack_sdk.errors.SlackApiError: The request to the Slack API failed. The server responded with: {'ok': False, 'error': 'already_reacted'}
                if not (type(err.response) is SlackResponse and "error" in err.response.data and err.response.data["error"] == "already_reacted"):
                    raise err

    else: # if user set no reactions, display a dialogue to inform the user that no reactions are set
        await client.views_open(
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
