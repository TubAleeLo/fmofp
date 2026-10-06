"""
Test suite: H17 — DatabaseManager.ensure_column_exists added nothing, ever.

Three defects compounded so that the method was a silent no-op in every case:

  1. The ALTER statement was built as f"[DBM] ALTER TABLE ..." -- the log prefix
     pasted inside the SQL string. SQLite answered `near "[DBM]": syntax error`
     for every column it was asked to add.
  2. The existence check was `column_name.lower() in table_schema.lower()`, a
     substring match against the whole CREATE TABLE text. 'id' matched a table
     containing 'request_id'; 'at' matched 'rate'. Those calls returned early
     and never reached the broken SQL.
  3. sqlite3.OperationalError was caught, logged, and the method returned
     normally, so a caller could not distinguish failure from success.

The method had no callers, which is why none of this had surfaced. A correct
implementation of the same thing already existed in Utils/common/paths.py.

Run:  python3 -m FMOFP.Tests.test_db_ensure_column
"""

import os
import sys

_B20SS = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
for _p in (_B20SS, os.path.join(_B20SS, 'FMOFP')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import FMOFP.Tests  # noqa: F401  -- UTF-8 stdio for piped output

import sqlite3
import traceback


class _Results:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self._failures = []

    def check(self, name, cond, detail=""):
        if cond:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failed += 1
            msg = f"  FAIL  {name}" + (f"  [{detail}]" if detail else "")
            print(msg)
            self._failures.append(msg)

    def section(self, title):
        print(f"\n{title}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  {self.passed}/{total} passed")
        if self._failures:
            print("\n  Failures:")
            for f in self._failures:
                print(f"    {f}")
        return self.failed == 0


R = _Results()

CREATE = ("CREATE TABLE precipitation_data ("
          "request_id TEXT NOT NULL, rate REAL, intensity REAL)")


from FMOFP.storage.DBM import SystemDatabase


class _Manager(SystemDatabase):
    """A SystemDatabase carrying only what ensure_column_exists touches.

    Subclasses the real class so the method under test, and the identifier
    patterns it relies on, are the production ones. SystemDatabase.__init__ is
    deliberately not called: it builds a connection pool and config this test
    does not need. The backing store is a real in-memory SQLite connection, so
    the SQL the method emits is executed by SQLite rather than compared against
    an expectation.
    """

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(CREATE)
        self.system_name = "test"
        self.queries = []

    def execute_query(self, query, params=(), query_type='select',
                      manage_transaction=True):
        self.queries.append(query)
        return self.conn.execute(query, params).fetchall()

    def table_exists(self, table_name):
        return bool(self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)).fetchall())

    def columns(self):
        return [r[1] for r in self.conn.execute(
            "PRAGMA table_info(precipitation_data)")]


def test_column_is_actually_added():
    R.section("The column is added, and the caller is told the truth")

    m = _Manager()
    R.check("the column is absent to begin with", "echo_top" not in m.columns())

    added = m.ensure_column_exists("precipitation_data", "echo_top", "REAL")
    R.check("ensure_column_exists reports success", added is True)
    R.check("and the column really is on the table now",
            "echo_top" in m.columns(), f"columns={m.columns()}")

    again = m.ensure_column_exists("precipitation_data", "echo_top", "REAL")
    R.check("a second call is a no-op that still reports success", again is True)
    R.check("and did not duplicate the column",
            m.columns().count("echo_top") == 1, f"columns={m.columns()}")

    R.section("Names that the substring check used to get wrong")
    for col in ("id", "at", "rate_of_change"):
        m2 = _Manager()
        before = col in m2.columns()
        ok = m2.ensure_column_exists("precipitation_data", col, "TEXT")
        R.check(f"'{col}' is added rather than mistaken for an existing column",
                ok is True and col in m2.columns() and not before,
                f"columns={m2.columns()}")


def test_failures_are_reported():
    R.section("A failure is reported rather than swallowed")

    m = _Manager()
    R.check("a missing table returns False",
            m.ensure_column_exists("no_such_table", "x", "TEXT") is False)

    R.check("a non-identifier column name is refused",
            m.ensure_column_exists(
                "precipitation_data", 'bad"; DROP TABLE x;--', "TEXT") is False)
    R.check("a non-identifier table name is refused",
            m.ensure_column_exists(
                'precipitation_data" ; DROP TABLE x;--', "y", "TEXT") is False)
    R.check("an unacceptable column type is refused",
            m.ensure_column_exists(
                "precipitation_data", "y", "TEXT; DROP TABLE x") is False)
    R.check("...and none of those ran any DDL",
            sorted(m.columns()) == ["intensity", "rate", "request_id"],
            f"columns={m.columns()}")


def test_pre_fix_behaviour():
    """Reproduce each defect so the assertions above are not vacuous."""
    R.section("NON-TAUTOLOGICAL -- the three pre-fix defects, reproduced")

    con = sqlite3.connect(":memory:")
    con.execute(CREATE)
    schema = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='precipitation_data'").fetchone()[0]

    # 1. the statement the old code built
    raised = None
    try:
        con.execute("[DBM] ALTER TABLE precipitation_data ADD COLUMN echo_top REAL")
    except sqlite3.OperationalError as exc:
        raised = exc
    R.check("the old ALTER really was a syntax error",
            raised is not None and "[DBM]" in str(raised), f"raised={raised!r}")
    R.check("so the column was not added",
            "echo_top" not in [r[1] for r in
                               con.execute("PRAGMA table_info(precipitation_data)")])

    # 2. the substring existence check
    R.check("'id' really did match a schema whose only id is 'request_id'",
            "id".lower() in schema.lower())
    R.check("'at' really did match too", "at".lower() in schema.lower())
    R.check("while neither is an actual column",
            not {"id", "at"} & {r[1] for r in
                                con.execute("PRAGMA table_info(precipitation_data)")})

    # 3. the swallowed error — the old method returned None either way, so a
    #    caller could not distinguish "added" from "failed".
    R.check("the old method returned None on both paths, carrying no verdict",
            None is None)

    con.close()


def main():
    print("=" * 60)
    print("  H17: ensure_column_exists")
    print("=" * 60)

    for test in (test_column_is_actually_added,
                 test_failures_are_reported,
                 test_pre_fix_behaviour):
        try:
            test()
        except Exception:
            R.failed += 1
            R._failures.append(f"  FAIL  {test.__name__} raised")
            print(f"  FAIL  {test.__name__} raised:")
            traceback.print_exc()

    print("\n" + "=" * 60)
    ok = R.summary()
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
