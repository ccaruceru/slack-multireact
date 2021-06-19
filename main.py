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
    # add static /img route for debugging
    app.web_app().add_routes([web.static("/img", "img")])
    port = int(os.environ.get("PORT", 3000))
    logging.info("Listening on port %d", port)
    app.start(port)

# TODO: PEP 8
# TODO: tests
