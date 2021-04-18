import os
import logging
from multi_reaction_add import handler, app


def entrypoint(request):
    """Google Cloud Function HTTP main entrypoint
    Args:
        request (flask.Request): The request object.
        <https://flask.palletsprojects.com/en/1.1.x/api/#incoming-request-data>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <https://flask.palletsprojects.com/en/1.1.x/api/#flask.make_response>.
    """
    return handler.handle(request)


if __name__ == "__main__":
    """Main entrypoint for local development
    """
    if "LOCAL_DEVELOPMENT" in os.environ:
        port = int(os.environ.get("LOCAL_PORT", 3000))
        logging.info(f"Listening on port {port}")
        app.start(port)
