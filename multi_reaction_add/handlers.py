# -*- coding: utf-8 -*-
"""Handles incoming Slack API calls.

Attributes:
    storage_client (Client): client used to access Google Cloud Storage
    bucket (google.cloud.storage.bucket.Bucket): a GCS bucket for user data
    slack_client_id (str): Current Slack application client id
    app (AsyncApp): Connector between Slack API and application logic
"""

import os
import logging
from asyncio import sleep

from google.cloud.storage import Client
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.starlette.async_handler import AsyncSlackRequestHandler
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_bolt.context.respond.async_respond import AsyncRespond
from slack_bolt.context.async_context import AsyncBoltContext
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from starlette.applications import Starlette
from starlette.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
from starlette.routing import Route, Mount

from multi_reaction_add.internals import EmojiOperator
from multi_reaction_add.internals import setup_logger, build_home_tab_view, delete_users_data, user_data_key, check_env
from multi_reaction_add.oauth.installation_store.google_cloud_storage import GoogleCloudStorageInstallationStore
from multi_reaction_add.oauth.state_store.google_cloud_storage import GoogleCloudStorageOAuthStateStore

# ------------
# Bolt section
# ------------

check_env()  # check for env vars
setup_logger()  # setup json logging for google cloud
storage_client = Client()  # initialize the Google Storage client
bucket = storage_client.bucket(os.environ["USER_DATA_BUCKET_NAME"])
slack_client_id = os.environ["SLACK_CLIENT_ID"]
slash_command = os.environ.get("SLACK_SLASH_COMMAND", "/multireact")
# initialize the app with the OAuth configuration
app = AsyncApp(
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    oauth_settings=AsyncOAuthSettings(
        # token_rotation_expiration_minutes=1000000,  # enable this to test token rotation
        install_page_rendering_enabled=False,
        client_id=slack_client_id,
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=["commands", "emoji:read"],  # scopes needed for bot operations
        # scopes needed for operations on behalf of user
        user_scopes=["reactions:read", "reactions:write"],
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
app_handler = AsyncSlackRequestHandler(app)


# https://api.slack.com/interactivity/slash-commands, https://slack.dev/bolt-python/concepts#commands
@app.command(slash_command)
async def save_or_display_reactions(
        ack: AsyncAck,
        client: AsyncWebClient,
        command: dict,
        respond: AsyncRespond,
        logger: logging.Logger) -> None:
    """Handler for slack commands.

    Examples:
      "/multireact"      - display reactions for curent user, or inform that none is set
      "/multireact text" - set reactions for current user

    Args:
        ack (AsyncAck): function to inform slack that an event has been received
        client (AsyncWebClient): an initialzied slack web client to communicate with slack API
        command (dict): json payload with information about the command triggered by the user
                        E.g.
                            {'token': 'MKxqqxT4PQMBnyNJdjAocKOF', 'team_id': '<tid>', 'team_domain': '<tname>', 'channel_id': 'D01T36EUQTT', 'channel_name': 'directmessage', 'user_id': 'U01SWNKJR6G', 'user_name': 'user.name', 'command': '/multireact', 'text': ':+1::eyes::clap:', 'api_app_id': '<id>', 'is_enterprise_install': 'false', 'response_url': 'https://hooks.slack...WRrsPnTqV8QtqZ5Un0', 'trigger_id': '1917238991...9a29a6da4'} # pylint: disable=line-too-long
                            {'api_app_id': '<id>', 'channel_id': 'D01SQA99362', 'channel_name': 'directmessage', 'command': '/multireact', 'enterprise_id': '<eid>', 'enterprise_name': '<ename>', 'is_enterprise_install': 'false', 'response_url': 'https://hooks.slack....UFIRvQgGs0', 'team_domain': '<tname>', 'team_id': '<tid>', 'token': 'wF8MDfFS8BLd30KFYLT1MlZa', 'trigger_id': '1995489393941.299118...b1d2b8f830', 'user_id': 'U01SXA059B5', 'user_name': '<uname>'}
        respond (AsyncRespond): function that sends an ephemeral response for slack commands
        logger (Logger): optional logger passed to all handlers
    """
    await ack()  # commands must be acknowledged with ack() to inform Slack your app has received the event.
    user_id = command["user_id"]
    key = user_data_key(slack_client_id=slack_client_id,
                        enterprise_id=(
                            command["enterprise_id"] if "enterprise_id" in command else None),
                        team_id=command["team_id"],
                        user_id=user_id)
    blob = bucket.blob(key)

    if "text" in command and command["text"].strip():  # this command has some text in it => will save new reactions
        # sanitize the mesage from user and select only reactions
        reactions = await EmojiOperator.get_valid_reactions(command["text"], client, logger)
        if len(reactions) > 23:
            # inform user when reaction limit reached
            # https://slack.com/intl/en-se/help/articles/206870317-Use-emoji-reactions
            await respond("Slow down! You tried to save more than 23 reactions :racing_car:\n"
                          "Try using less reactions this time :checkered_flag:")
            logger.info("User %s tried to add >23 reactions", user_id)

        elif len(reactions) == 0:  # no reactions found in the given text
            await respond("Oh no! You did not provide any valid reactions :open_mouth:\n"
                          "Make sure you type the reactions starting with `:`, "
                          "or use the Emoji button (:slightly_smiling_face:) to add one.")
            logger.info("User %s set no valid reactions", user_id)

        else:  # valid reactions were given to be saved
            reactions = " ".join(reactions)
            blob.upload_from_string(reactions)
            await respond("Great! Your new reactions are saved :sunglasses: "
                          f"Type `{slash_command}` to see them at any time.")
            logger.info("User %s saved %s", user_id, reactions)

    else:  # otherwise, report to user any reactions they have
        if blob.exists():  # display any reactions the user has saved
            reactions = blob.download_as_text(encoding="utf-8")
            reactions = " ".join([f":{r}:" for r in reactions.split(" ")])
            await respond(f"Your current reactions are: {reactions}. "
                          f"Type `{slash_command} <new list of emojis>` to change them.")
            logger.info("User %s loaded %s", user_id, reactions)

        else:  # or say that user doesn't have any
            await respond("You do not have any reactions set :anguished:\n"
                          f"Type `{slash_command} <list of emojis>` to set one.")
            logger.info("User %s has no reactions", user_id)


@app.shortcut("add_reactions")
async def add_reactions(
    ack: AsyncAck,
    shortcut: dict,
    client: AsyncWebClient,
    logger: logging.Logger,
    context: AsyncBoltContext) -> None:
    """Handler for message shortcut functionality.

    Adds users saved reactions to the message mentioned in the shortcut activity.

    Args:
        ack (AsyncAck): function to inform slack that an event has been received
        shortcut (dict): json payload with information about the shortcut triggered by the user
                         E.g.
                            {'type': 'message_action', 'token': 'MKxqqxT4PQMBnyNJdjAocKOF', 'action_ts': '1617307130.812650', 'team': {'id': '<tid>', 'domain': '<domain>'}, 'user': {'id': 'U01SWNKJR6G', 'username': 'user.name', 'team_id': '<tid>', 'name': 'User Name'}, 'channel': {'id': 'C01S9QDFYNT', 'name': 'general'}, 'is_enterprise_install': False, 'enterprise': None, 'callback_id': 'add_reactions', 'trigger_id': '1921893944...3e6a446fbc18', 'response_url': 'https://hooks.slack...L9Vdrbee00sZG', 'message_ts': '1617307089.003400', 'message': {'client_msg_id': '6f9e6469-1...70b17af92b', 'type': 'message', 'text': 'asdfghjkl', 'user': 'U01SWNKJR6G', 'ts': '1617307089.003400', 'team': '<tid>', 'blocks': [{'type': 'rich_text', 'block_id': 'm3V', 'elements': [{'type': 'rich_text_section', 'elements': [{'type': 'text', 'text': 'asdfghjkl'}]}]}]}} # pylint: disable=line-too-long
                            {'action_ts': '1619339417.302061', 'callback_id': 'add_reactions', 'channel': {'id': 'C01V7KXNRRS', 'name': '<chname>'}, 'enterprise': {'id': '<eid>', 'name': '<ename>'}, 'is_enterprise_install': False, 'message': {'blocks': [...], 'client_msg_id': '437b2675-6524-4724-a...69a4e0b9f6', 'team': '<tid>',  'text': '210', 'ts': '1619339414.000200', 'type': 'message', 'user': 'U01SXA059B5'}, 'message_ts': '1619339414.000200', 'response_url': 'https://hooks.slack....tkt5yMCogg', 'team': {'domain': '<domain>', 'enterprise_id': '<eid>', 'enterprise_name': '<ename>',  'id': '<tid>'}, 'token': 'wF8MDfFS8BLd30KFYLT1MlZa', 'trigger_id': '1991796659910.299118...7619ad8bd4', 'type': 'message_action', 'user': {'id': 'U01SXA059B5', 'name': '<uname>', 'team_id': '<tid>', 'username': '<uname>'}}
        client (AsyncWebClient): an initialzied slack web client to communicate with slack API
        logger (Logger): optional logger passed to all handlers
        context (AsyncBoltContext): a dictionary added to all handlers which can be used to enrich events with
                                    additional information
    """
    await ack()  # commands must be acknowledged with ack() to inform Slack your app has received the event.
    user_id = shortcut["user"]["id"]
    message_ts = shortcut["message_ts"]
    channel_id = shortcut["channel"]["id"]
    key = user_data_key(slack_client_id=slack_client_id,
                        enterprise_id=(
                            shortcut["enterprise"]["id"] if shortcut["enterprise"] else None),
                        team_id=shortcut["team"]["id"],
                        user_id=user_id)
    blob = bucket.blob(key)
    reactions = None
    if blob.exists():
        reactions = blob.download_as_text(encoding="utf-8")

    if reactions:  # if user has any reactions saved, add them to the message
        reactions = reactions.split(" ")  # was saved as space separated string
        orig_reactions = reactions.copy()  # keep list wth original positions
        # alter context to post on users's behalf
        # https://slack.dev/java-slack-sdk/guides/bolt-basics#use-web-apis--reply-using-say-utility
        client.token = context.user_token
        # get user reactions on message
        used_reactions = await EmojiOperator.get_user_reactions(client, channel_id, message_ts, user_id)
        # compute list of remaining reactions
        to_react = list(set(reactions) - set(used_reactions))
        # put reactions back in order
        to_react = [r for r in orig_reactions if r in to_react]
        for reaction in to_react:
            try:
                await client.reactions_add(
                    channel=channel_id,
                    timestamp=message_ts,
                    name=reaction
                )
                logger.info("User %s reacted %s on message %s from channel %s",
                            user_id, reaction, message_ts, channel_id)
            except SlackApiError:
                logger.exception("Failed to add reaction %s on message %s for user %s from channel %s",
                                 reaction, message_ts, user_id, channel_id)
            finally:
                await sleep((50+5)//60)  # Slack Api Tier 3 limit

    else:  # if user set no reactions, display a dialogue to inform the user that no reactions are set
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
                            "text": ("You do not have any reactions set :anguished:\n"
                                     f"Type `{slash_command} <list of emojis>` in the chat to set one.")
                        }
                    }
                ]
            }
        )
        logger.info("User %s has no reactions", user_id)


async def handle_token_revocations(event: dict, context: AsyncBoltContext, logger: logging.Logger) -> None:
    """Deletes the token given by the OAuth process when a user removes the app.

    It revokes the installation tokens and removes the user emoji data too.

    Args:
        event (dict): payload with user or bot ids
        context (AsyncBoltContext): a dictionary added to all handlers which can be used to enrich events with
                                    additional information
        logger (Logger): optional logger passed to all handlers
    """
    user_ids = event["tokens"].get("oauth")
    if user_ids is not None and len(user_ids) > 0:
        await delete_users_data(bucket, slack_client_id, context.enterprise_id, context.team_id, user_ids)
        logger.info("Deleted user data for %s", user_ids)



@app.event("app_home_opened")
async def update_home_tab(
    client: AsyncWebClient,
    event: dict,
    logger: logging.Logger,
    request: AsyncBoltRequest) -> None:
    """Invoked when a user opens up the app Home Tab. It displays a help page for this app.

    Args:
        client (AsyncWebClient): an initialzied slack web client to communicate with slack API
        event (dict): payload from slack server for app home opened event
                      E.g.
                          {'type': 'app_home_opened', 'user': 'U01SWNKJR6G', 'channel': 'D02FP4JLJ56', 'tab': 'home', 'event_ts': '1632136426.209403'}  # pylint: disable=line-too-long
        logger (Logger): optional logger passed to all handlers
        request (AsyncBoltRequest): entire request payload from slack server
    """
    user_id = event["user"]
    # https://cloud.google.com/appengine/docs/standard/python/how-requests-are-routed#domain_name_is_included_in_the_request_data
    if "host" in request.headers and len(request.headers["host"]) > 0:
        view = build_home_tab_view(slash_command, app_url=f"https://{request.headers['host'][0]}")
    else:
        view = build_home_tab_view(slash_command)

    await client.views_publish(
        user_id=user_id,  # Use the user ID associated with the event
        view=view
    )
    logger.info("User %s opened home tab", user_id)


app.event("tokens_revoked")(app.default_tokens_revoked_event_listener(), handle_token_revocations)
app.event("app_uninstalled")(app.default_app_uninstalled_event_listener())

# -----------------
# Starlette section
# -----------------


async def events(request: Request) -> Response:
    """Handles Bolt app http requests.

    Args:
        request (Request): HTTP request

    Returns:
        Response: ASGI response
    """
    return await app_handler.handle(request)


async def install(request: Request) -> Response:
    """Handles Slack app installation http request.

    Args:
        request (Request): HTTP request

    Returns:
        Response: ASGI response
    """
    return await app_handler.handle(request)


async def oauth_redirect(request: Request) -> Response:
    """Handles OAuth authorization http request.

    Args:
        request (Request): HTTP request

    Returns:
        Response: ASGI response
    """
    return await app_handler.handle(request)


async def warmup(request: Request) -> Response:  # pylint: disable=unused-argument
    """Handle Google App Engine warmup requests.

    https://cloud.google.com/appengine/docs/standard/python3/configuring-warmup-requests

    Args:
        request (Request): HTTP request

    Returns:
        Response: ASGI response
    """
    return PlainTextResponse("")


# https://github.com/slackapi/bolt-python/blob/main/examples/starlette/async_oauth_app.py
api = Starlette(
    routes=[
        Route("/slack/events", endpoint=events, methods=["POST"]),
        Route("/slack/install", endpoint=install, methods=["GET"]),
        Route("/slack/oauth_redirect", endpoint=oauth_redirect, methods=["GET"]),
        # add the warmup route and static img route
        Route('/_ah/warmup', endpoint=warmup, methods=["GET"]),
        Mount('/img', app=StaticFiles(directory="resources/img")),
    ]
)
