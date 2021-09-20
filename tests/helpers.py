# -*- coding: utf-8 -*-
"""Module holding boilerplate code for running the tests"""

import os
from contextlib import contextmanager, ContextDecorator
from unittest.mock import patch

@contextmanager
def patch_import() -> ContextDecorator:
    """Returns a context manager where the google storage client library has been patched for testing

    Yields:
        ContextDecorator: a context manager
    """
    # necessary OS env vars for handlers.py module
    keys = ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET",
            "SLACK_INSTALLATION_GOOGLE_BUCKET_NAME", "SLACK_STATE_GOOGLE_BUCKET_NAME", "USER_DATA_BUCKET_NAME"]
    # patch google storage client call and os env vars
    with patch.dict(os.environ, {k:"" for k in keys}) as mock_env:  # pylint: disable=unused-variable
        with patch("google.cloud.storage.Client") as mock_storage_client:
            yield mock_storage_client
