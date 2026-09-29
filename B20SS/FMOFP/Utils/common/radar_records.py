"""Book-keeping rows kept in the radar measurement tables, and how to exclude them.

``precipitation_data`` holds one row per measured precipitation point, and every
column in it is ``NOT NULL``.  The precipitation handler also writes a second
kind of row into the same table: a "collection" row, whose job is to tie a batch
of points back to the request that produced them, so that the whole batch can be
found later by the original ``request_id``.  It is a link record, not a
measurement, and its ``position_x``/``position_y``/``rate``/``intensity`` columns
are filled with zeros purely because the schema forbids NULLs there.

Nothing distinguished those rows on the way back out, which had two consequences:

* A collection row read back as a precipitation point at ``(0, 0)`` -- ownship --
  with rate 0 and intensity 0, i.e. as a measured "no precipitation here"
  reading that the radar never took.
* Worse, the lookup in ``precipitation_response_service`` queries
  ``WHERE request_id = ?`` first and only falls back to the child pattern
  ``request_id LIKE ?`` when that comes back empty.  The collection row is stored
  under exactly the original ``request_id``, so the first query always matched
  it, the fallback never ran, and the real points in the batch were never
  returned at all.

Reads that want measurements must therefore exclude these rows.  Use
``MEASUREMENT_ONLY_SQL`` in the WHERE clause rather than spelling the predicate
out, so that the writer and the ten-odd readers cannot drift apart.
"""

# The value written into the 'type' column of a link record.
COLLECTION_RECORD_TYPE = "collection"

# Predicate restricting a query on precipitation_data to real measurements.
# Intended to be interpolated into a WHERE clause, e.g.
#     f"SELECT * FROM precipitation_data WHERE timestamp > ? AND {MEASUREMENT_ONLY_SQL}"
# It contains no parameters and no caller-supplied text.
MEASUREMENT_ONLY_SQL = f"type != '{COLLECTION_RECORD_TYPE}'"

__all__ = ["COLLECTION_RECORD_TYPE", "MEASUREMENT_ONLY_SQL"]
