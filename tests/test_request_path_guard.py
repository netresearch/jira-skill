# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""The client refuses a URL whose identifiers would retarget the request."""

from unittest import mock

import click
import pytest
from lib.client import (
    LazyJiraClient,
    UnsafeRequestPathError,
    _check_request_url,
    _patch_session_for_response_validation,
    check_issue_ref,
)

BASE = "https://jira.example.com/rest/api/2/issue"


@pytest.mark.parametrize(
    "url",
    [
        # jira-worklog.py delete PROJ-1 '../../PROJ-2' -> DELETE issue/PROJ-2
        f"{BASE}/PROJ-1/worklog/../../PROJ-2",
        # jira-worklog.py delete 'PROJ-1#' 42 -> DELETE issue/PROJ-1
        f"{BASE}/PROJ-1#/worklog/42",
        # jira-worklog.py delete 'PROJ-2?x=' 42 -> DELETE issue/PROJ-2
        f"{BASE}/PROJ-2?x=/worklog/42",
        f"{BASE}/PROJ-1/worklog/%2e%2e/%2E%2E/PROJ-2",
        f"{BASE}/./PROJ-1",
        # Tomcat strips the path parameter and then normalises the segment.
        f"{BASE}/PROJ-1/worklog/..;/..;/PROJ-2",
        f"{BASE}/PROJ-1/worklog/..%3Bx/..%3bx/PROJ-2",
        f"{BASE}/PROJ-1/worklog/..%2F..%2FPROJ-2",
        f"{BASE}/PROJ-1/worklog/..\\..\\PROJ-2",
        f"{BASE}/PROJ-1/worklog/..%5C..%5CPROJ-2",
    ],
)
def test_refuses_a_retargeting_url(url):
    with pytest.raises(UnsafeRequestPathError):
        _check_request_url(url)


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/PROJ-1/worklog/42",
        f"{BASE}/PROJ-1/worklog/42?adjustEstimate=leave",
        # The library puts some parameters into the path itself.
        f"{BASE}/PROJ-1?fields=labels",
        # params= are encoded, so a slash in a value arrives as %2F.
        "https://jira.example.com/rest/api/2/search?jql=summary+~+%22a%2Fb%22",
        "https://jira.example.com/rest/api/2/version/10001",
        f"{BASE}/PROJ-1/worklog/v1.2",
    ],
)
def test_passes_an_ordinary_url(url):
    _check_request_url(url)


def test_the_patched_session_sends_nothing_for_a_refused_url():
    client = mock.Mock()
    original = client._session.request
    original.side_effect = AssertionError("the request was sent")
    _patch_session_for_response_validation(client, "https://jira.example.com")

    with pytest.raises(UnsafeRequestPathError):
        client._session.request("DELETE", f"{BASE}/PROJ-1/worklog/../../PROJ-2")

    original.assert_not_called()


@pytest.mark.parametrize(
    "issue_key",
    [
        # jira-issue delete 'PROJ-1?deleteSubtasks=true' -> the library appends
        # &deleteSubtasks=false, and Jira reads the first value.
        "PROJ-1?deleteSubtasks=true",
        "PROJ-1/comment/7",
        "PROJ-1#",
        "../PROJ-2",
        "PROJ-1 ",
        "PROJ-٤٢",
        "",
        # download-all puts the value into a URL that bypasses the session check.
        "https://jira.example.com/browse/../../rest/api/2/issue/PROJ-2",
        "https://jira.example.com/browse/PROJ-1?deleteSubtasks=true",
        "https://jira.example.com/browse/PROJ-1#x",
        "https://jira.example.com/browse/PROJ-1/../PROJ-2",
        "https://jira.example.com/rest/api/2/issue/PROJ-1",
        "https://jira.example.com/jira/%2e%2e/browse/PROJ-1",
    ],
)
def test_with_context_refuses_what_is_not_an_issue_reference(issue_key):
    with pytest.raises(click.BadParameter):
        LazyJiraClient().with_context(issue_key=issue_key)


@pytest.mark.parametrize(
    "issue_key",
    [
        "PROJ-123",
        "proj-1",
        "AB_2-7",
        "10042",
        "https://jira.example.com/browse/WEB-99",
        "http://jira.example.com:8080/jira/browse/WEB-99",
    ],
)
def test_with_context_accepts_keys_ids_and_urls(issue_key):
    check_issue_ref(issue_key)
    LazyJiraClient().with_context(issue_key=issue_key)
