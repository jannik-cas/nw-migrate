from __future__ import annotations

import importlib
import sys
from unittest.mock import patch


def test_main_invokes_cli() -> None:
    with patch("nw_migrate.cli.main") as mock_main:
        sys.modules.pop("nw_migrate.__main__", None)
        importlib.import_module("nw_migrate.__main__")
        mock_main.assert_called_once()
