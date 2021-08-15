# -*- coding: utf-8 -*-
"""Slack application entrypoint for standalone run.

Example:
    $ python multi_reaction_add

TODO:
    * create new client for emoji update to avoid concurrency problems(?)
    * use X-Cloud-Trace-Context to group logs:
        https://cloud.google.com/appengine/docs/standard/python3/writing-application-logs#writing_structured_logs
"""

import os
import logging
from aiohttp import web

from multi_reaction_add.handlers import app
from multi_reaction_add.internals import check_env


if __name__ == "__main__":
    check_env()
    # add static /img route for debugging
    app.web_app().add_routes([web.static("/img", "resources/img")])
    port = int(os.environ.get("PORT", 3000))
    logging.info("Listening on port %d", port)
    app.start(port)
