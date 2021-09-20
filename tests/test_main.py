# -*- coding: utf-8 -*-
"""Tests for __main__.py"""

import os
from unittest import TestCase
from unittest.mock import patch, Mock
from tests.helpers import patch_import

with patch_import() as _:
    from multi_reaction_add.__main__ import main

class TestMain(TestCase):
    """Test the main method"""

    @patch("multi_reaction_add.__main__.check_env")
    @patch("multi_reaction_add.__main__.app")
    def test_main(self, app: Mock, check_env: Mock):
        """Test the main method"""
        # pylint: disable=no-self-use

        # test default port
        main()
        check_env.assert_called_once()
        app.start.assert_called_once_with(3000)

        app.reset_mock()

        # test custom port
        os.environ["PORT"] = "5454"
        main()
        app.start.assert_called_once_with(5454)
        del os.environ["PORT"]
