from codeplumb.extract.crossrefs import find_cross_refs
from codeplumb.extract.definitions import split_definitions
from codeplumb.extract.exceptions import split_exceptions


def test_split_exceptions_single_and_numbered():
    paras = [
        "Body para one.",
        "Exception: A single exception.",
        "Body para two.",
        "Exceptions:",
        "1. First.",
        "2. Second.",
        "Body para three.",
    ]
    body, exc = split_exceptions(paras)
    assert body == ["Body para one.", "Body para two.", "Body para three."]
    assert exc == ["Exception: A single exception.", "Exceptions:\n1. First.\n2. Second."]


def test_split_definitions():
    body = "ACCESSIBLE ROUTE. A continuous path.\n\nEXIT ACCESS. The part before an exit.\n\nFIRE AREA (NET). Bounded area."
    defs = split_definitions(body)
    assert [t for t, _ in defs] == ["ACCESSIBLE ROUTE", "EXIT ACCESS", "FIRE AREA (NET)"]
    assert defs[1][1] == "The part before an exit."


def test_split_definitions_needs_two_terms():
    assert split_definitions("ONLY ONE. Something.") == []


def test_find_cross_refs():
    text = "See Section 1010.1.1 and Sections 903.2.1 through 903.2.8; Table 1004.5 applies; Chapter 11 too. Section 1010.1.1 again."
    refs = find_cross_refs(text)
    assert ("Section 1010.1.1", "1010.1.1", "section") in refs
    assert ("Table 1004.5", "1004.5", "table") in refs
    assert ("Chapter 11", "11", "chapter") in refs
    assert sum(1 for r in refs if r[1] == "1010.1.1") == 1
    assert ("Sections 903.2.1", "903.2.1", "section") in refs
