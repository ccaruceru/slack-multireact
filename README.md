# About

Slack bot that allows users to add multiple reactions to a message. Written in Python using [Slack Bolt for Python](https://slack.dev/bolt-python/tutorial/getting-started).

<img src="docs/app.png" alt="logo" width="200"/>

# Usage

The bot exposes two APIs: a `/multireact` [command](https://slack.com/intl/en-se/help/articles/201259356-Slash-commands-in-Slack) and a `Multireact` [message Shortcut](https://slack.com/intl/en-se/help/articles/360004063011-Work-with-apps-in-Slack-using-shortcuts#message-shortcuts).

## Examples
- `/multireact` to view saved the reactions
<img src="docs/reaction-view.png" alt="reaction-view" width="500"/>

- `/multireact 🤠😎😼➕💯` to set a list of reactions
<img src="docs/reaction-save.png" alt="reaction-save" width="500"/>

- Add reactions on a message by going to `More Actions` -> `More message shortcuts` -> `Multireact`
<img src="docs/reaction-none.png" alt="reaction-none" width="500"/>
<img src="docs/reaction-menu.png" alt="reaction-menu"/>
<img src="docs/reaction-add.png" alt="reaction-add" width="500"/>


# Google Cloud deployment

The deployment process consists in creating two Google Cloud components: A [Function](https://cloud.google.com/functions/docs/quickstart-python) and several [Buckets](https://cloud.google.com/storage/docs/key-terms#buckets).

## Google Storage buckets

The application requires 3 GCS buckets to store temporary data for the oauth process, app installation data for each user and another bucket for user emoji data.

Sample commands to create the buckets:
```bash
gsutil mb -c STANDARD -l europe-west1 -b on gs://multi-reaction-add-userdata

gsutil mb -c STANDARD -l europe-west1 -b on gs://multi-reaction-add-oauthstate

gsutil mb -c STANDARD -l europe-west1 -b on gs://multi-reaction-add-installation
```

## Service account

Create a service account that the function will use to access the GCS buckets.
```bash
gcloud iam service-accounts create sa-multireact-slack-app --description="SVC account for running Google cloud functions for multireact slack app" --display-name="SA Multireact Slack App"
```
Get the service account full name:
```bash
gcloud iam service-accounts list
```
Grant permissions for each bucket:
```bash
gsutil iam ch serviceAccount:sa-multireact-slack-app@king-multireact-slack-app-dev.iam.gserviceaccount.com:roles/storage.objectAdmin gs://multi-reaction-add-userdata

gsutil iam ch serviceAccount:sa-multireact-slack-app@king-multireact-slack-app-dev.iam.gserviceaccount.com:roles/storage.objectAdmin gs://multi-reaction-add-oauthstate

gsutil iam ch serviceAccount:sa-multireact-slack-app@king-multireact-slack-app-dev.iam.gserviceaccount.com:roles/storage.objectAdmin gs://multi-reaction-add-installation
```

## Create Slack application

### Interactivity & Shortcuts
- Add `<bot address>/slack/events` to **Request URL** (_can be added after the Function has been deployed - see [Google Cloud Function](#google-cloud-function) section_)
- **Create New Shortcut**
    - with **On messages** type
    - that has the Callback ID named `add_reactions`
<img src="docs/create-shortcut.png" alt="create-shortcut" width="500"/>

### Slash commands
- **Create New Command**
    - Command is `/multireact`
    - Request URL is `<bot address>/slack/events` (_can be added after the Function has been deployed - see [Google Cloud Function](#google-cloud-function) section_)
<img src="docs/create-command.png" alt="create-command" width="500"/>

### OAuth & Permissions
- **Add New Redirect URL** and use `<bot address>/slack/oauth_redirect` (_can be added after the Function has been deployed - see [Google Cloud Function](#google-cloud-function) section_)
- **Scopes**
    - **Bot Token Scopes**: Add and OAuth scope for `commands` (might be already added)
<img src="docs/add-scopes.png" alt="add-scope" width="500"/>

### App Home
Disable all options

### Basic Information
Add relevant description under **Display Information**

## Environment variables

Environment variables for the Google Cloud Function are set in [.env.yaml](.env.yaml) file. Mandatory variables from the app's **Basic Information** page:
- SLACK_CLIENT_ID: the **Client ID** 
- SLACK_CLIENT_SECRET: the **Client Secret**
- SLACK_SIGNING_SECRET: the **Signing Secret**
<img src="docs/app-credentials.png" alt="app-credentials" width="500"/>

Along with Google Cloud Storage bucket names:
- SLACK_INSTALLATION_GOOGLE_BUCKET_NAME: name of a bucket used to store Slack app install data per user
- SLACK_STATE_GOOGLE_BUCKET_NAME: bucket name for storing temporary OAuth state
- USER_DATA_BUCKET_NAME: bucket for user emoji data

Optional:
- LOG_LEVEL: log verosity. defaults to `INFO`

### Google Cloud Function

Deploy the function using the following command:
```bash
gcloud functions deploy multireact-add-slack-app --runtime python38 --trigger-http --allow-unauthenticated --env-vars-file .env.yaml --region=europe-west1 --source=. --entry-point=entrypoint --service-account=sa-multireact-slack-app@king-multireact-slack-app-dev.iam.gserviceaccount.com
```

**Notes**
- Google Cloud Functions and Google Cloud Build services must be enabled for the project
- `--allow-unauthenticated` flag implies that the user who deploys the function has **Security Admin** role in order to assing `roles/cloudfunctions.invoker` to `allUsers` for the deployed function, otherwise the following warning will be seen: _WARNING: Setting IAM policy failed_

Describe the function to get the HTTPS endpoint:
```bash
gcloud functions describe multireact-add-slack-app
```

# Local development
To start development for this app, it is recommended to have installed **Python 3.8**, [ngrok](https://ngrok.com/download) and [Google Cloud SDK](https://cloud.google.com/sdk/docs/install), then run:
- `pip install -r requirements.txt`
- in a sepparate terminal run `ngrok http 3000` and take a note of the _generated https address_
    - **note**: sometimes the VPN client will prevent ngrok from establishing a connection
- setup a slack application according to [Create Slack application](#create-slack-application) section, using ngrok's _generated https address_
    - when running the application locally, the HTTP endpoints created by Bolt framework are:
        - **/slack/events** - used as _Request URL_ for incoming slack API requests (commands and shortcuts)
        - **/slack/install** - simple interface which allows a user to install the app to a workspace and start the OAuth flow
        - **/slack/oauth_redirect** - endpoint used by Slack to complete the OAuth flow (the _Redirect URL_ under [OAuth & Permissions](#oauth-&-Permissions) section)
- create GCS buckets described in [Google Storage buckets](#google-storage-buckets)
- create a service account similar to [Service account](#service-account) and generate a key for the account:
```bash
gcloud iam service-accounts keys create sa-multireact-key.json --iam-account=sa-multireact-slack-app@king-multireact-slack-app-dev.iam.gserviceaccount.com
```
- set environment variables according to [Environment variables](#environment-variables) section, along with:
    - LOCAL_DEVELOPMENT: set to any value to run the application in standalone mode and not in a Google Cloud Function
    - GOOGLE_APPLICATION_CREDENTIALS: path to a json file with credentials for an account with permissions to GCS buckets
    - LOCAL_PORT: port where the app exposes an http endpoint for local development. defaults to 3000
- `python main.py` to run the app
- go to "_generated https address_/slack/install" to install the app to the workspace and start interracting like in the [Usage](#usage) section.

## Debugging with VS Code

Use the following `.vscode/launch.json` file to setup a debug configuration for the app:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Slack Bot",
            "type": "python",
            "request": "launch",
            "program": "main.py",
            "console": "integratedTerminal",
            "env": {
                "SLACK_CLIENT_ID": "clientid",
                "SLACK_CLIENT_SECRET": "clientsecret",
                "SLACK_SIGNING_SECRET": "signingsecret",
                "LOG_LEVEL": "INFO",
                "LOCAL_DEVELOPMENT": "true",
                "LOCAL_PORT": "3000",
                "GOOGLE_APPLICATION_CREDENTIALS": "sa-multireact-key.json",
                "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME": "multi-reaction-add-installation",
                "SLACK_STATE_GOOGLE_BUCKET_NAME": "multi-reaction-add-oauthstate",
                "USER_DATA_BUCKET_NAME": "multi-reaction-add-userdata"
            }
        }
    ]
}
```

Then press `F5` to start debugging.

## More

More info about how to setup a local environment can be found [here](https://slack.dev/bolt-python/tutorial/getting-started), and documentation about the Slack Bolt for Python APIs can be found [here](https://slack.dev/bolt-python/concepts).

Whenever you change how the interraction with Slack API is made, don't forget to check out the [Slack API Tier limits](https://api.slack.com/docs/rate-limits) (the various api calls/minute rates) and set pauses in the app accordingly, otherwise Slack will return a `HTTP 429 Too Many Requests`.
