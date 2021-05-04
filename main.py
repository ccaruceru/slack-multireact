import os
import logging
from multi_reaction_add import app
from aiohttp import web


async def entrypoint() -> web.Application:
    """Handler for Gunicorn server

    Returns:
        aiohttp.web.Application: The initialized aiohttp server instance
    """
    return app.web_app()


if __name__ == "__main__":
    """Main entrypoint that starts the server
    """
    port = int(os.environ.get("PORT", 3000))
    logging.info(f"Listening on port {port}")
    app.start(port)


# TODO: handle token revoked and app uninstalled events: https://gist.github.com/seratch/d81a445ef4467b16f047156bf859cda8#file-main-py-L50-L65
