# Changelog

## Unreleased

- Added concrete SQLx 0.9 PostgreSQL support through the existing driver-neutral
  connection, statement, value, result and structured-error API. Includes
  PostgreSQL-aware named SQL, typed nulls, checked integer/REAL parameters, strict
  native value mappings, raw/failed transaction state and cancellation recovery.
  The package profile now also requires `networking`.
- Added a PostgreSQL 18 Compose test stack with a dedicated bind mount. Managed
  runs stop the stack and clear old test data at the start, then retain database
  files after success or failure for inspection. SQLite coverage remains in the
  default managed run.

- Refactored SQL scanner byte dispatch into a switch while preserving quote,
  comment, parameter, and statement-termination behavior; covered ordinary
  minus/slash characters and their rejection after a statement terminator.

- This is a breaking replacement of the earlier `terrane/dbkit` package, not an
  API-preserving upgrade: the baseline used namespace
  `/terrane/dbkit/sqlite`, SQLx 0.8.6, and exposed `open`, `config(path,
  create-if-missing)`, a free `prepare`, and `bind-bytes`. It did not include
  the current `streaky/dbkit` namespace, named-parameter scanner, typed values,
  or HTTP-server example.
- Migration: replace `open` with `connect` and construct a `config` with
  `driver` (default `sqlite`) and `database` (default `:memory:`). The old
  `create-if-missing` option is gone: a nonempty filesystem path opens or
  creates the SQLite database, provided its parent directory already exists.
  Preparation is now connection-bound (`await connection.prepare; sql`), and
  values/bindings use the current typed factories and named-binding API. Review
  transaction and scanner contracts before porting behavior.
- Rebuilt the SQLite runtime on SQLx 0.9 with connection-bound preparation and
  reusable dbkit metadata/bindings. Execution is non-persistent and preparation
  clears native cached metadata to avoid SQLx's stale-column schema-change panic;
  compiled execution-cache reuse is intentionally suspended until an upstream fix.
- Documented typed Rust boundaries, SQLx locked-handle inspection of SQLite
  autocommit state, SQLite storage-class value behavior, buffered row results,
  and sanitized structured error fields. Native errors remain in throwable
  causes when rethrown; rendered/uncaught diagnostics may therefore contain
  SQLx text and native codes.
- The current release includes the named-parameter scanner, typed-value
  behavior, transaction limitations, and HTTP-server example; these were not
  retained from the baseline API. No mapped-query API or independent native
  statement-handle contract is provided.
- Fixed cancellation cleanup to restore native ownership synchronously, with no
  locked-handle await in finalizers. Transaction state is explicitly unknown after
  cancellation until another live operation refreshes it.
- Made statement closure slot-local, idempotent, and safe during other operations;
  returning metadata cannot revive a closed slot.
- Refreshed result metadata on reuse after schema changes and translated failed
  ordinal access to dbkit errors instead of Rust `expect` panics.
- Switched the HTTP example to per-request connections against a shared database
  file; documented shared-connection busy failures and SQLx connection defaults.
- Matched SQLite bracket-identifier termination and trailing form-feed whitespace.
- Expanded native scenarios for cancellation, sibling failure, concurrent close
  and drop, raw/implicit rollback, schema changes, false binding and 120 wrappers.
