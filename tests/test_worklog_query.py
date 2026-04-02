"""Tests for jira-worklog-query.py — cross-cutting worklog query tool."""

import importlib.util
import sys
from pathlib import Path

# Add scripts to path for lib imports
_test_dir = Path(__file__).parent
_scripts_path = _test_dir.parent / "skills" / "jira-communication" / "scripts"
sys.path.insert(0, str(_scripts_path))


def _load_script():
    """Load jira-worklog-query via importlib."""
    path = _scripts_path / "utility" / "jira-worklog-query.py"
    spec = importlib.util.spec_from_file_location("jira_worklog_query", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
