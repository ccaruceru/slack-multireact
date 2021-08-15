# -*- coding: utf-8 -*-
"""Slack application entrypoint for both gunicorn and standalone run.

Examples:
    $ python main.py
    $ gunicorn --bind :3000 --workers 1 --threads 8 --timeout 0 --worker-class aiohttp.GunicornWebWorker main:entrypoint

TODO:
    * move main.py to handlers.py (update docs)
    * create new client for emoji update to avoid concurrency problems(?)
    * use X-Cloud-Trace-Context to group logs: https://cloud.google.com/appengine/docs/standard/python3/writing-application-logs#writing_structured_logs # pylint: disable=line-too-long
"""

import os
import logging
from aiohttp import web

from multi_reaction_add.handlers import app
from multi_reaction_add.internals import check_env


async def entrypoint() -> web.Application:
    """Handles Gunicorn server entrypoint.

    Returns:
        aiohttp.web.Application: The initialized aiohttp server instance
    """
    check_env()
    return app.web_app()


if __name__ == "__main__":
    check_env()
    # add static /img route for debugging
    app.web_app().add_routes([web.static("/img", "resources/img")])
    port = int(os.environ.get("PORT", 3000))
    logging.info("Listening on port %d", port)
    app.start(port)
