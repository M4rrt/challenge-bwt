# Own database, with the Company boundary living in code

**Status:** accepted

The chat service has its own database and no access to the monolith's. The
foreign keys to Company, User and CompanyUser stop existing and become opaque
identifiers. The alternative — same database, separate schema — would preserve
referential integrity, but would deliver the cost of operating two deployments
without the independence that pays for it.

## Consequences

**Company isolation leaves the database and becomes code.** In the source module
it was a queryset invariant, and its docstring said in so many words that
isolation lived there and nowhere else, precisely so that no call site would
have to remember to apply it. Here there is no such floor: the company arrives
as a token claim and every read path has to filter by it explicitly. This is the
central risk of the architecture, and it is why the service's first test is the
one that fails if that filtering is absent.

The source module's authorisation leaned on `User` subclasses through
multi-table inheritance — an `isinstance` check decided who reads the staff-only
thread, and there are six subclasses. None of that crosses the boundary: the
user's kind becomes a claim, and the rule that an unclassifiable reader lands on
the narrow side has to be rewritten by hand on top of it.

Profiles (name, avatar) come to exist as a local copy, because the chat list's
search filters by participant name and you cannot paginate a list filtered by a
column the database does not have. That puts personal data in the chat's
database, which changes what that database is for data-protection and backup
retention purposes. The rule that keeps this honest lives in
`docs/decisions.md`: no message table stores the sender's name.
