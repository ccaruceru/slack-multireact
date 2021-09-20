# -*- coding: utf-8 -*-
"""Slack application entrypoint for standalone run.

Example:
    $ python multi_reaction_add

Todo:
    * create new client for emoji update to avoid concurrency problems(?)
    * use X-Cloud-Trace-Context to group logs:
        https://cloud.google.com/appengine/docs/standard/python3/writing-application-logs#writing_structured_logs
"""

import os
import logging

from multi_reaction_add.handlers import app
from multi_reaction_add.internals import check_env


def main():
    """Main entrypoint for standalone module run.

    Example:
        $ python -m multi_react_add
    """
    check_env()
    port = int(os.environ.get("PORT", 3000))
    logging.info("Listening on port %d", port)
    app.start(port)


if __name__ == "__main__":
    main()
