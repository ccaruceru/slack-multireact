import os
import logging
from multi_reaction_add import flask_app


if __name__ == "__main__":
    """Main entrypoint that starts the server
    """
    port = int(os.environ.get("PORT", 3000))
    logging.info(f"Listening on port {port}")
    flask_app.run(debug=True, host="0.0.0.0", port=port)
