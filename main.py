import os
import logging
from multi_reaction_add import app
from aiohttp import web


def _check_env() -> None:
    """Checks if mandatory environment variables are set

    Raises:
        Exception: when one or more environment variables are missing
    """
    keys = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET",
        "SLACK_BOT_USER_OAUTH_TOKEN", "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME",
        "SLACK_STATE_GOOGLE_BUCKET_NAME", "USER_DATA_BUCKET_NAME"]
    missing = [key for key in keys if key not in os.environ.keys()]
    if missing:
        raise Exception(f"The following environment variables are not set: {missing}")


async def entrypoint() -> web.Application:
    """Handler for Gunicorn server

    Returns:
        aiohttp.web.Application: The initialized aiohttp server instance
    """
    _check_env()
    return app.web_app()


if __name__ == "__main__":
    """Main entrypoint that starts the server
    """
    _check_env()
    # add static /img route for debugging
    app.web_app().add_routes([web.static("/img", "img")])
    port = int(os.environ.get("PORT", 3000))
    logging.info("Listening on port %d", port)
    app.start(port)

# TODO: PEP 8
# TODO: tests
