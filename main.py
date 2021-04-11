import logging
import os
import re
import threading
from pathlib import Path
from time import sleep

from slack_bolt import App
from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_sdk.errors import SlackApiError
from slack_sdk.oauth.installation_store import FileInstallationStore
from slack_sdk.oauth.state_store import FileOAuthStateStore
from slack_bolt.adapter.cherrypy import SlackRequestHandler # https://slack.dev/bolt-python/concepts#adapters
import cherrypy


TIER2_LIMIT_SEC = (20-2)/60 # Slack tier 2 api rate limit: 20/min
TIER3_LIMIT_SEC = (50-5)/60 # Slack tier 3 api rate limit: 50/min
TIER4_LIMIT_SEC = 110/60 # Slack tier 4 api rate limit: 100+/min

# list of all emojis available in this team
ALL_EMOJIS = []
EMOJI_TOKEN = None

# dir for user reactions
logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
USER_DATA_DIR = Path(os.environ.get('APP_HOME', '.')) / 'userdata'
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
logging.info(f"User data directory set to {USER_DATA_DIR.absolute()}")
# dir for application oauth tokens
APP_DATA_DIR = Path(os.environ.get('APP_HOME', '.')) / 'appdata'
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
logging.info(f"OAuth tokens directory set to {APP_DATA_DIR.absolute()}")

# Initialize the app with the OAuth configuration
app = App(
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    oauth_settings=OAuthSettings(
        client_id=os.environ["SLACK_CLIENT_ID"],
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=["commands", "emoji:read"], # scopes needed for bot operations
        user_scopes=["reactions:write"], # scopes needed for operations on behalf of user
        installation_store=FileInstallationStore(base_dir=APP_DATA_DIR),
        state_store=FileOAuthStateStore(expiration_seconds=600, base_dir=APP_DATA_DIR)
    )
)
handler = SlackRequestHandler(app)


class SlackApp(object):
    @cherrypy.expose
    @cherrypy.tools.slack_in()
    def events(self, **kwargs):
        """Handles /slack/events which are all incoming slack API calls made by users

        Returns:
            Response: a utf-8 byte array with an HTTP response for the event triggered by the user
        """
        return handler.handle()


    @cherrypy.expose
    @cherrypy.tools.slack_in()
    def install(self, **kwargs):
        """Handles /slack/install and starts Slack OAuth flow (i.e. user installs the app)

        Returns:
            bytes: a utf-8 byte array with an HTTP response containing a payload to request app authorization for a user
        """
        return handler.handle()


    @cherrypy.expose
    @cherrypy.tools.slack_in()
    def oauth_redirect(self, **kwargs):
        """Handles /slack/oauth_redirect to save the user OAuth credentials after app usage has been authorized

        Returns:
            bytes: a utf-8 byte array with an HTTP response to redirect the user to Slack after user authorized the app usage
        """
        return handler.handle()


    @cherrypy.expose
    def healthcheck(self):
        """Handles /healthcheck api endpoint

        Returns:
            str: A success message
        """
        return "App is running"


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
    global ALL_EMOJIS, EMOJI_TOKEN

    reactions = re.findall(r":[a-z0-9-_\+']+:", text) # find all :emoji: strings
    reactions = list(dict.fromkeys(reactions)) # remove duplicates
    if not reactions:
        return []

    reactions = [r[1:-1] for r in reactions] # strip the colons
    if not ALL_EMOJIS: # populate emoji list if first time call
        EMOJI_TOKEN = client.token # save the token for later emoji.list api calls
        ALL_EMOJIS = _get_reactions_in_team(client)

    return [r for r in reactions if r in ALL_EMOJIS]


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
    user_file = USER_DATA_DIR / user_id

    if "text" in command: # this command has some text in it => will save new reactions
        reactions = _get_valid_reactions(command["text"], client) # sanitize the mesage from user and select only reactions
        if len(reactions) > 23: # inform user when reaction limit reached: https://slack.com/intl/en-se/help/articles/206870317-Use-emoji-reactions
            try:
                respond(("Slow down! You tried to save more than 23 reactions :racing_car:\nTry using less reactions this time :checkered_flag:"))
                logger.info(f"User {user_id} tried to add >23 reactions")
            finally:
                sleep(TIER4_LIMIT_SEC)
        elif len(reactions) == 0: # no reactions found in the given text
            try:
                respond(("Oh no! You did not provide any valid reactions :open_mouth:\nMake sure you type the reactions starting with `:`,"
                        " or use the Emoji button (:slightly_smiling_face:) to add one."))
                logger.info(f"User {user_id} set no valid reactions")
            finally:
                sleep(TIER4_LIMIT_SEC)
        else: # valid reactions were given to be saved
            reactions = " ".join(reactions)
            user_file.open("w").write(reactions)
            try:
                respond("Great! Your new reactions are saved :sunglasses: Type `/multireact` to see them at any time.")
                logger.info(f"User {user_id} saved {reactions}")
            finally:
                sleep(TIER4_LIMIT_SEC)
    else: # otherwise, report to user any reactions they have
        if user_file.exists(): # display any reactions the user has saved
            reactions = user_file.open().read()
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

    user_file = USER_DATA_DIR / user_id
    reactions = None
    if user_file.exists():
        reactions = user_file.open().read()

    if reactions: # if user has any reactions saved, add them to the message
        for reaction in reactions.split(" "): # saved as a whitespace separated string
            try:
                client.token = context.user_token # alter context to post on users's behalf: https://slack.dev/java-slack-sdk/guides/bolt-basics#use-web-apis--reply-using-say-utility
                try:
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


def update_emoji_list():
    """Updates the global EMOJIS list with latest from slack api. It does the actual API call if a user provided a valid token for the call
    """
    global ALL_EMOJIS

    while True:
        try:
            logging.info("Start emoji update")
            if EMOJI_TOKEN:
                old_token = app.client.token
                app.client.token = EMOJI_TOKEN
                ALL_EMOJIS = _get_reactions_in_team(app.client)
                logging.info(ALL_EMOJIS)
                app.client.token = old_token
                logging.info("Emoji update finished")
            else:
                logging.info("There is no valid token to use for emoji update")
        except SlackApiError as err:
            logging.error(err, exc_info=True)

        sleep(60) # 1 min


if __name__ == "__main__":
    """Main entry point to start the app
    """
    port = int(os.environ.get("PORT", 3000))
    logging.info(f"Listening on port {port}")
    update_thread = threading.Thread(target=update_emoji_list, name="EmojiUpdate", daemon=True) # daemon=don't wait for it when program exits
    update_thread.start()
    cherrypy.config.update({
        'global': {
            'server.socket_host': '0.0.0.0',
            'server.socket_port': port,
        }
    })
    if "ENVIRONMENT" in os.environ and os.environ["ENVIRONMENT"]:
        logging.info(f"Setting cherrypy environemnt to {os.environ['ENVIRONMENT']}")
        cherrypy.config.update({ 'global': { 'environment' : os.environ["ENVIRONMENT"] }})

    cherrypy.quickstart(SlackApp(), "/slack") # TODO: POST /slack/events HTTP/1.1" 404 30
    # TODO: USE SOCKET MODE https://slack.dev/bolt-python/concepts#socket-mode
