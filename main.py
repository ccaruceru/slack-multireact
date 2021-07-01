# -*- coding: utf-8 -*-
"""Slack application entrypoint for both gunicorn and standalone run.

Examples:
    $ python main.py
    $ gunicorn --bind :3000 --workers 1 --threads 8 --timeout 0 --worker-class aiohttp.GunicornWebWorker main:entrypoint

TODO:
    * tests
    * create new client for emoji update to avoid concurrency problems(?)
    * use X-Cloud-Trace-Context to group logs: https://cloud.google.com/appengine/docs/standard/python3/writing-application-logs#writing_structured_logs # pylint: disable=line-too-long
"""

import os
import logging
from aiohttp import web

from multi_reaction_add import app


def _check_env() -> None:
    """Checks if mandatory environment variables are set.

    Raises:
        Exception: when one or more environment variables are missing
    """
    keys = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET", "SLACK_BOT_USER_OAUTH_TOKEN",
            "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME", "SLACK_STATE_GOOGLE_BUCKET_NAME", "USER_DATA_BUCKET_NAME"]
    missing = [key for key in keys if key not in os.environ.keys()]
    if missing:
        raise Exception(f"The following environment variables are not set: {missing}")


async def entrypoint() -> web.Application:
    """Handles Gunicorn server entrypoint.

    Returns:
        aiohttp.web.Application: The initialized aiohttp server instance
    """
    _check_env()
    return app.web_app()


if __name__ == "__main__":
    _check_env()
    # add static /img route for debugging
    app.web_app().add_routes([web.static("/img", "img")])
    port = int(os.environ.get("PORT", 3000))
    logging.info("Listening on port %d", port)
    app.start(port)
