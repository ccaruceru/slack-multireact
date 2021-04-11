# About

Slack bot that allows users to add multiple reactions to a message. Written in Python using [Slack Bolt for Python](https://slack.dev/bolt-python/tutorial/getting-started).

<img src="docs/app.png" alt="logo" width="200"/>

# Usage

The bot exposes two APIs: a `/multireact` [command](https://slack.com/intl/en-se/help/articles/201259356-Slash-commands-in-Slack) and a `Multireact` [message Shortcut](https://slack.com/intl/en-se/help/articles/360004063011-Work-with-apps-in-Slack-using-shortcuts#message-shortcuts).

## Examples
- `/multireact` to view saved the reactions

TBA: screenshots
- `/multireact 🤠😎😼➕💯` to set a list of reactions
- Add reactions on a message by going to `More Actions` -> `More message shortcuts` -> `Multireact`

# Deployment

## Create Slack application

### Interactivity & Shortcuts
- Add `<bot address>/slack/events` to **Request URL**
- **Create New Shortcut**
    - with **On messages** type
    - that has the Callback ID named `add_reactions`
<img src="docs/create-shortcut.png" alt="create-shortcut" width="500"/>

### Slash commands
- **Create New Command**
    - Command is `/multireact`
    - Request URL is `<bot address>/slack/events`
<img src="docs/create-command.png" alt="create-command" width="500"/>

### OAuth & Permissions
- **Add New Redirect URL** and use `<bot address>/slack/oauth_redirect`
- **Scopes**
    - **Bot Token Scopes**: Add and OAuth scope for `commands` (might be already added)
<img src="docs/add-scopes.png" alt="add-scope" width="500"/>

### App Home
- Disable all options

### Basic Information
- add relevant description under **Display Information**

## Registry

Build and push the image to [King's registry](https://registry.corp.midasplayer.com/harbor/projects), which is a [Harbor](https://kingfluence.com/display/DDT/Harbor+-+VMware+docker+registry) server.
- `docker build -t registry.corp.midasplayer.com/king/multireact-add:<TAG> .`
- `docker push registry.corp.midasplayer.com/king/multireact-add:<TAG>`

## Environment variables
Mandatory variables from the app's **Basic Information** page:
- SLACK_SIGNING_SECRET: the **Signing Secret**
- SLACK_CLIENT_ID: the **Client ID** 
- SLACK_CLIENT_SECRET: the **Client Secret**
<img src="docs/app-credentials.png" alt="app-credentials" width="500"/>

Optional:
- ENVIRONMENT: the environment for cherrypy web server (defaults to `production` in Docker)
- APP_HOME: path to where the app data should be persisted. defaults to current directory (`.`) or `/data` in Docker
- PORT: port the app should listen to incoming slack events. defaults to 3000
- LOG_LEVEL: log verosity. defaults to `INFO`

## Docker command
```bash
docker run --rm -it -e SLACK_SIGNING_SECRET=<signing secret> -e SLACK_CLIENT_ID=<client id> -e SLACK_CLIENT_SECRET=<client secret> -p 3000:3000 -v </local/path>:/data multireact
```

## Kubernetes

**UNDER CONSTRUCTION**

The application is deployed on a [Kubernetes cluster](https://kingfluence.com/display/DDT/Kubernetes) maintained by Cloud Foundation team located at https://k8s.int.cloud.king.com/, under **sgt-bot** namespace.

General guildelines:
https://kingfluence.com/display/DDT/Adding+TLS+To+Your+Service

Use the following [yaml deployment file](deployment.yaml) to deploy the app.

TBA: use Vault slack secret

# Local development
To start development for this app, it is recommended to have installed **Python 3.8** and **ngrok**, then run:
- `pip install -r requirements.txt`
- in a sepparate terminal run `ngrok http 3000`
- setup a slack application according to [Create Slack application](#create-slack-application) section
- set environment variables according to [Environment variables](#environment-variables) section
- `python main.py` to run the app

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
                "SLACK_SIGNING_SECRET": "signingsecret",
                "SLACK_CLIENT_ID": "clientid",
                "SLACK_CLIENT_SECRET": "clientsecret",
                "APP_HOME": "/tmp/mutlireact",
                "PORT": "3000",
                "LOG_LEVEL": "INFO"
            }
        }
    ]
}
```

Then press `F5` to start debugging.

## More

More info about how to setup a local environment can be found [here](https://slack.dev/bolt-python/tutorial/getting-started), and documentation about the Slack Bolt for Python APIs can be found [here](https://slack.dev/bolt-python/concepts).

Whenever you change how the interraction with Slack API is made, don't forget to check out the [Slack API Tier limits](https://api.slack.com/docs/rate-limits) (the various api calls/minute rates) and set pauses in the app accordingly, otherwise Slack will return a `HTTP 429 Too Many Requests`.
