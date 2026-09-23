"""The glossary in `CONTEXT.md` is the only vocabulary the service speaks.

A glossary nobody checks is a glossary that decays one merge at a time: the
word `Conversation` survived the move to FastAPI because nothing failed when it
did. This test is what makes the naming a property of the code rather than a
habit — a new module, route or column carrying an avoided word names itself
here.

The scan is textual on purpose. The words have to be absent from identifiers,
strings, route paths and comments alike, and no type checker sees all four.
"""

import re
from pathlib import Path

# The words `CONTEXT.md` lists under _Avoid_ for Chat, with their plurals.
# `DM` and `NewChat` are left out: two letters and a camel-case fragment match
# far more prose than they catch.
AVOIDED = re.compile(r"\b(conversations?|conversas?|rooms?|salas?)\b", re.IGNORECASE)

_BACKEND = Path(__file__).resolve().parent.parent
_SCANNED = (_BACKEND / "app", _BACKEND / "tests")


def _offences(source: Path) -> list[str]:
    return [
        f"{source.relative_to(_BACKEND)}:{number}: {line.strip()}"
        for number, line in enumerate(source.read_text().splitlines(), start=1)
        if AVOIDED.search(line)
    ]


def test_no_avoided_word_survives_in_the_service_or_its_tests():
    """`alembic/versions/` is excluded, and has to be: a migration is a dated record.

    The migration that created `conversations` describes a schema that really
    did exist under that name, and rewriting it would make `alembic upgrade`
    from an empty database build tables the later migrations cannot find. The
    rename lives in a new migration instead.
    """
    sources = sorted(path for directory in _SCANNED for path in directory.rglob("*.py"))
    offences = [
        offence
        for source in sources
        if source != Path(__file__).resolve()
        for offence in _offences(source)
    ]

    assert sources, "scanned nothing, so an empty offence list would mean nothing"
    assert offences == [], "these speak a word the glossary avoids:\n" + "\n".join(offences)
