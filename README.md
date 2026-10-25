# dbkit

`streaky/dbkit` is a Terrane-native relational database package with SQLite and
PostgreSQL drivers behind one driver-neutral connection API. It is an optional
package, not Terrane's canonical database layer. It requires the current Terrane
compiler and `build`, `filesystem`, `threads`, and `networking` capabilities.

## Getting started

Add dbkit as a local path dependency in `package.toml`:

```toml
package = "notes"
executor = "threaded"
rust-toolchain = "pinned"

[namespaces]
app = "src"

[profile]
name = "notes"
capabilities = ["build", "filesystem", "threads", "networking"]

[terrane-dependencies.streaky.dbkit]
path = "../dbkit"
```

The basic example in `examples/basic` uses this same dependency declaration with
`path = "../.."`. Here is a small complete program using the public
`/streaky/dbkit` namespace:

```terrane
namespace app

from /streaky/dbkit import config, connect, connection, integer-value, text-value

async function read-note string; database shared ref connection
    selected = await database.prepare; 'SELECT body FROM notes WHERE id = :id'
    selected.bind; 'id', (integer-value; 1)
    results = await selected.query;
    record = results.fetch;
    if record != none
        return (record.named; 'body').as-text;
    return ''

async function main;
    database = await connect; (instance config; 'sqlite', ':memory:')
    await database.execute; 'CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)'
    await database.begin;
    inserted = await database.prepare; 'INSERT INTO notes (id, body) VALUES (:id, :body)'
    inserted.bind; 'id', (integer-value; 1)
    inserted.bind; 'body', (text-value; 'hello dbkit')
    changed = await inserted.execute;
    print; changed.affected
    await database.commit;
    print; (await read-note; database)
    await database.begin;
    await database.execute; 'DELETE FROM notes'
    await database.rollback;
    print; (await read-note; database)
    await database.close;
```

## API overview

`config` selects a runtime driver (`sqlite` by default) and database setting
(`:memory:` by default). SQLite accepts a local filename; PostgreSQL accepts a
PostgreSQL URL. `connect` returns a shared dbkit `connection`; concrete SQLx 0.9
connections stay private. `available-drivers` reports `sqlite` and `postgres`.
MySQL remains unavailable, and unknown names fail without a fallback. No
database-shaped Rust facade, pool, ORM, query builder, migration framework, or
streaming cursor is provided. Driver-neutral access does not promise portable SQL.

See the [Drivers overview](docs/src/records/drivers/index.yaml) for separate SQLite,
PostgreSQL, and MySQL reference pages and their current availability.

`prepare` genuinely prepares SQL through SQLx's connection-bound `prepare_with`.
dbkit retains owned SQL metadata and reusable bindings, not an independent native
statement handle. See the driver reference for backend-specific behavior and
limitations.

Use `bind` to assign a value using a name without `:`, and
`clear-bindings` to clear assignments. Rebinding replaces the previous value.
Repeated `:name` placeholders are accepted and each occurrence uses the same
binding; every occurrence must have a binding before execution. Binding an
unknown name fails, so surplus names are rejected. Named SQL uses the selected
driver's scanner: SQLite rejects foreign placeholder/cast syntax, while PostgreSQL
preserves `::` casts, dollar strings, nested comments and array/JSON operators.
Only one statement may be supplied. See each driver's reference for exact rules.

The [shared API reference](docs/src/records/api/database.yaml) records the narrow
typed native boundaries and their retirement conditions. Transaction inspection
uses actual backend state, including raw SQL, not a separate depth counter.
Cancellation cleanup restores ownership synchronously without native awaits.
After cancellation, `in-transaction` reports `transaction-state-unknown` until
another live operation refreshes state, rather than returning a stale boolean.

Values have strict null, integer, real, text, bytes and bool factories; fetch kinds
follow the selected driver's mapping. PostgreSQL preserves booleans, while SQLite
stores them as integers. There is no implicit text/numeric conversion. Query
results are fully buffered; exhaustion returns `none`, distinct from SQL NULL.
Rows support positional and named access; missing indexes/names and ambiguous
duplicate column names raise `database-error`.

Connections and statements can be explicitly closed; destructors also release
resources. Closing a connection rolls back an active transaction and closes
registered statement wrappers. Nested transactions are unsupported. Buffered
result sets survive closure. A shared connection can be passed to helpers, but
overlapping operations are rejected as busy rather than run concurrently.

Catch `database-error`, then use `error-details; failure` to read its `code`,
`operation`, human-readable `detail`, `driver`, and `native-code`. This follows
HTTP-server's structured throwable pattern because typed catches currently
expose the base throwable view. Native failures are translated to a sanitized
`database` category in these structured fields; `native-code` is empty rather
than parsed from native text. Rethrowing inside `catch` also preserves the
original native error as the throwable cause, so `failure.render` and uncaught
diagnostics may include native SQLx text and codes. Do not treat the cause chain
as sanitized or expose it as a stable structured field contract. See the
[structured manual](docs/src/manual.yaml) for the API and native integration boundaries.

## Verify

With the current optimized compiler at `target/release/terrane`, run:

```console
target/release/terrane test packages/dbkit
target/release/terrane run packages/dbkit/examples/basic
python packages/dbkit/tests/test_database.py --terrane target/release/terrane -v
packages/dbkit/tests/run_tests.sh -v
target/release/terrane run packages/dbkit/examples/http -- 127.0.0.1:3000
```

The Python suites use only the standard library. The managed runner additionally
requires Docker Engine and Compose: it runs unit, SQLite and PostgreSQL coverage,
clears the dedicated PostgreSQL bind directory at the start, and retains its files
after stopping the stack. See the [PostgreSQL test-stack reference](docs/src/records/drivers/postgresql.yaml)
for storage and inspection details. The direct SQLite suite needs no Docker.
The HTTP example prints its bound URL; `GET /notes` reads seeded data through dbkit.
