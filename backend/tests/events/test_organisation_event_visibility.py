"""Unit tests for SCRUM-7 "See only my own organisation's events".

AC1: an Event Organiser's event list holds only their client organisation's event
requests. AC2: another organisation's request, asked for by its reference, is refused
with the same 404 as a reference that doesn't exist (ADR-0012). AC3: organisers of the
same organisation see the same requests, whoever submitted them. A request filed under
no organisation (from before migration 0007) is in nobody's list and opens for nobody
(ADR-0013), and an organiser whose account has no organisation is refused both with a
403 (ADR-0020).

The services run against ``db_session``, so the filters are real SQL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.common.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.events.models import EventRequest
from app.modules.events.services import (
    CoordinatorContact,
    OrganiserEventRecord,
    OrganiserWithoutOrganisationError,
    get_event_record_for_organiser,
    get_event_request_for_organiser,
    list_event_requests_for_organiser,
)

pytestmark = pytest.mark.scrum_7

MakeEventRequest = Callable[..., EventRequest]

#: In client organisation 3, as ``saved_users`` links them.
ORGANISER_ID = 7
#: Also in client organisation 3.
COLLEAGUE_ID = 8
#: In client organisation 4.
OTHER_ORGANISATION_ORGANISER_ID = 6
#: An account from before SCRUM-66, linked to no organisation.
UNLINKED_ORGANISER_ID = 10

#: A request filed under no organisation, as those from before migration 0007 are.
UNFILED_REFERENCE = "EVR-DDDDDDDD"


def _references(event_requests: list[EventRequest]) -> set[str]:
    """Which requests a list holds; the order is covered by the SCRUM-19 tests."""
    return {event_request.reference for event_request in event_requests}


def _assert_not_found(exc_info: pytest.ExceptionInfo[NotFoundError]) -> None:
    """The refusal looks exactly like an unknown reference (ADR-0012).

    The message matters: a missing user account is also a 404, but a different one.
    """
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Event request not found."


def _assert_refused_as_unlinked(
    exc_info: pytest.ExceptionInfo[OrganiserWithoutOrganisationError],
) -> None:
    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == "organiser_without_organisation"


@pytest.fixture()
def requests_of_two_organisations(
    other_organisers: list[User], make_event_request: MakeEventRequest, save: Callable[..., None]
) -> list[EventRequest]:
    """Three saved requests: two in organisation 3 and one in organisation 4.

    ``EVR-AAAAAAAA`` by organiser 7 and ``EVR-CCCCCCCC`` by colleague 8 are
    organisation 3's; ``EVR-BBBBBBBB`` by organiser 6 is organisation 4's.
    """
    event_requests = [
        make_event_request(reference="EVR-AAAAAAAA", organiser_id=ORGANISER_ID),
        make_event_request(
            reference="EVR-BBBBBBBB",
            organiser_id=OTHER_ORGANISATION_ORGANISER_ID,
            organisation_id=4,
        ),
        make_event_request(reference="EVR-CCCCCCCC", organiser_id=COLLEAGUE_ID),
    ]
    save(*event_requests)
    return event_requests


@pytest.fixture()
def save_unfiled_request(
    make_event_request: MakeEventRequest, save: Callable[..., None]
) -> Callable[[int], EventRequest]:
    """Save ``EVR-DDDDDDDD`` by the given organiser, filed under no organisation."""

    def _save(organiser_id: int) -> EventRequest:
        event_request = make_event_request(
            reference=UNFILED_REFERENCE, organiser_id=organiser_id, organisation_id=None
        )
        save(event_request)
        return event_request

    return _save


# --------------------------------------------------------------------------
# AC1 — the list holds only the caller's organisation's requests
# --------------------------------------------------------------------------


def test_the_list_holds_only_the_callers_organisations_requests(
    requests_of_two_organisations: list[EventRequest],
) -> None:
    organisation_three = list_event_requests_for_organiser(ORGANISER_ID)
    organisation_four = list_event_requests_for_organiser(OTHER_ORGANISATION_ORGANISER_ID)

    assert _references(organisation_three) == {"EVR-AAAAAAAA", "EVR-CCCCCCCC"}
    assert _references(organisation_four) == {"EVR-BBBBBBBB"}


def test_a_request_with_no_organisation_appears_in_no_list_not_even_its_submitters(
    saved_users: list[User],
    make_event_request: MakeEventRequest,
    save: Callable[..., None],
    save_unfiled_request: Callable[[int], EventRequest],
) -> None:
    save(make_event_request(reference="EVR-AAAAAAAA"))
    save_unfiled_request(ORGANISER_ID)

    listed = list_event_requests_for_organiser(ORGANISER_ID)

    assert _references(listed) == {"EVR-AAAAAAAA"}


def test_an_organiser_without_an_organisation_is_refused_the_list(
    other_organisers: list[User], save_unfiled_request: Callable[[int], EventRequest]
) -> None:
    # Their own request has no organisation either; matching "no organisation" to
    # "no organisation" would hand it back instead of refusing.
    save_unfiled_request(UNLINKED_ORGANISER_ID)

    with pytest.raises(OrganiserWithoutOrganisationError) as exc_info:
        list_event_requests_for_organiser(UNLINKED_ORGANISER_ID)

    _assert_refused_as_unlinked(exc_info)


# --------------------------------------------------------------------------
# AC2 — another organisation's request is refused
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "open_request",
    [get_event_request_for_organiser, get_event_record_for_organiser],
    ids=["request", "record"],
)
def test_another_organisations_request_is_refused_as_not_found(
    requests_of_two_organisations: list[EventRequest], open_request: Callable[..., Any]
) -> None:
    with pytest.raises(NotFoundError) as exc_info:
        open_request(OTHER_ORGANISATION_ORGANISER_ID, "EVR-AAAAAAAA")

    _assert_not_found(exc_info)


def test_a_request_with_no_organisation_is_not_found_even_by_its_submitter(
    saved_users: list[User], save_unfiled_request: Callable[[int], EventRequest]
) -> None:
    save_unfiled_request(ORGANISER_ID)

    with pytest.raises(NotFoundError) as exc_info:
        get_event_request_for_organiser(ORGANISER_ID, UNFILED_REFERENCE)

    _assert_not_found(exc_info)


def test_an_organiser_without_an_organisation_cannot_open_a_request(
    other_organisers: list[User], save_unfiled_request: Callable[[int], EventRequest]
) -> None:
    save_unfiled_request(UNLINKED_ORGANISER_ID)

    with pytest.raises(OrganiserWithoutOrganisationError) as exc_info:
        get_event_request_for_organiser(UNLINKED_ORGANISER_ID, UNFILED_REFERENCE)

    _assert_refused_as_unlinked(exc_info)


# --------------------------------------------------------------------------
# AC3 — organisers of one organisation see the same requests
# --------------------------------------------------------------------------


def test_organisers_of_the_same_organisation_see_the_same_list(
    requests_of_two_organisations: list[EventRequest],
) -> None:
    organisers_list = list_event_requests_for_organiser(ORGANISER_ID)
    colleagues_list = list_event_requests_for_organiser(COLLEAGUE_ID)

    assert _references(organisers_list) == {"EVR-AAAAAAAA", "EVR-CCCCCCCC"}
    assert _references(colleagues_list) == _references(organisers_list)


def test_a_colleague_can_open_a_request_they_did_not_submit(
    other_organisers: list[User],
    submit_valid_request: Callable[..., EventRequest],
    lead_assigns: Callable[[EventRequest, int], None],
) -> None:
    submitted = submit_valid_request()  # by organiser 7
    lead_assigns(submitted, 3)  # the Lead gives it to coordinator 3 (SCRUM-95 AC3)

    record = get_event_record_for_organiser(COLLEAGUE_ID, "EVR-AAAAAAAA")

    assert record == OrganiserEventRecord(
        event_request=submitted,
        coordinator=CoordinatorContact(
            full_name="Coordinator Three", email="coordinator3@example.com"
        ),
    )
