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

# TODO: allow only skin tone modifiers + parse messages withouth any spaces
# TODO: app home with instructions how to use the app
