# Changelog

## Unreleased

- Completed the SQLite runtime cutover to SQLx 0.9 while preserving the public
  `streaky/dbkit` API. SQLx owns connection-bound preparation and the compiled
  SQLite statement cache; dbkit retains owned statement metadata and executes
  cached statements through SQLx `query_with`.
- Documented the narrowly typed SQL/metadata/index bridges, SQLx locked-handle
  inspection of SQLite autocommit state, SQLite storage-class value behavior,
  buffered row results, and sanitized native error translation. PostgreSQL and
  MySQL remain unavailable; native error codes remain unavailable.
- Retained the existing named-parameter scanner limits, typed-value behavior,
  transaction limitations, and HTTP-server consumer example. No mapped-query
  API or independent native statement-handle contract is provided.
