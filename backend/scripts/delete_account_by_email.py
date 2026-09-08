"""Delete one account straight from the database, by email.

For the one case the API cannot handle: an account whose password is gone.
`DELETE /api/auth/account` needs that account's own token and password, and
`/api/admin` is read-only, so a throwaway whose generated password was never
recorded can only be removed here.

**This is the same operation as the endpoint, not a shortcut around it.**
`delete_account` in app/auth/router.py is `db.delete(user)` and a commit -- it
relies entirely on FK cascades, and there is no session table to clear because
JWTs are stateless. This does exactly that, through the same models.

⚠️ Prefer Neon's SQL Editor for a one-off. It needs no connection string at all,
so nothing has to be copied anywhere: console.neon.tech -> the project -> SQL
Editor. This script is for when you want the checks below done for you, or the
same thing against a local database.

⚠️ The connection string is read from the environment or a file, NEVER passed as
an argument, so it stays out of shell history and out of the process list:

    DATABASE_URL          if already set, used as-is
    ~/.macros-prod-db-url otherwise

⚠️ Do not put a production URL in backend/.env. scripts/dev.sh sources that file
with `set -a`, so it would be exported into local development -- dev.sh's own
comment warns about exactly this. A path under $HOME cannot be sourced by
anything else or committed by accident.

Write the file without the value reaching your shell history -- it goes to
stdin, not to argv:

    cat > ~/.macros-prod-db-url    # paste, then Ctrl-D
    chmod 600 ~/.macros-prod-db-url

Dry run by default; nothing is written without --delete.

    venv/bin/python scripts/delete_account_by_email.py <email>
    venv/bin/python scripts/delete_account_by_email.py <email> --delete
"""
import os
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# app.db is imported for its side effect, not its contents: it registers the
# Engine "connect" hook that issues PRAGMA foreign_keys=ON. SQLite does not
# enforce foreign keys by default, so without this a delete against a local
# database would silently ORPHAN every child row instead of cascading -- and
# report success. Postgres needs no such help.
from app import db as _db  # noqa: F401
from app.models import Base, User

URL_FILE = os.path.expanduser("~/.macros-prod-db-url")


def owned_tables():
    """Every table carrying a user_id, read from the metadata.

    Derived rather than listed. A hand-written list is exactly the thing that
    goes stale the next time a feature adds a table -- and this script's whole
    job is proving nothing was left behind, which a stale list cannot do.
    """
    return [t for t in Base.metadata.sorted_tables if "user_id" in t.c]


def counts(session, user_id):
    return {
        table.name: session.scalar(
            select(func.count()).select_from(table).where(table.c.user_id == user_id)
        )
        for table in owned_tables()
    }


def resolve_url() -> str:
    url = os.environ.get("DATABASE_URL") or ""
    source = "$DATABASE_URL"
    if not url and os.path.exists(URL_FILE):
        url = open(URL_FILE).read().strip()
        source = URL_FILE
    if not url:
        sys.exit(
            f"No connection string. Set DATABASE_URL or write it to {URL_FILE}.\n"
            "Do not pass it as an argument, and do not put it in backend/.env."
        )
    # Report where it came from and what it points at, never the credential. A
    # string quietly read from the wrong place is how you delete from the wrong
    # database, and the host is the cheapest way to notice before you do.
    host = url.split("@")[-1].split("/")[0] if "@" in url else url
    print(f"connection: {source} -> {host}\n")
    return url


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) != 1:
        sys.exit(__doc__)
    email = args[0]
    commit = "--delete" in sys.argv[1:]

    engine = create_engine(resolve_url())
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            total = session.scalar(select(func.count()).select_from(User.__table__))
            print(f"No account with email {email!r}. Nothing to do.")
            print(f"{total} accounts in this database.")
            return

        user_id = user.id
        print(f"user_id {user_id}  {user.email}  joined {user.created_at}")
        print("\nrows owned:")
        for name, n in counts(session, user_id).items():
            print(f"  {name:20} {n}")

        if not commit:
            print("\nDRY RUN — nothing written. Re-run with --delete to remove it.")
            return

        session.delete(user)
        session.commit()

        # "The account is gone" and "nothing of theirs is left" are two
        # different claims, and only the second one is the job. On Postgres an
        # uncascaded child would have aborted the delete above; on SQLite
        # without the pragma it would not have, which is why both are checked.
        gone = session.scalar(select(User).where(User.id == user_id)) is None
        orphans = {name: n for name, n in counts(session, user_id).items() if n}
        total = session.scalar(select(func.count()).select_from(User.__table__))
        print(f"\nuser row gone: {gone}")
        print(f"orphaned rows: {orphans or 'none — every cascade fired'}")
        print(f"{total} accounts remain.")
        if not gone or orphans:
            sys.exit("SOMETHING IS LEFT")


if __name__ == "__main__":
    main()
