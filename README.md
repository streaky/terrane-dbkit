# dbkit

`streaky/dbkit` is a Terrane-native relational database package. It currently
provides a real local SQLite driver behind a driver-neutral connection API; it is
an optional package, not Terrane's canonical database layer. The package requires
the current Terrane compiler and `build`, `filesystem`, and `threads` capabilities.

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
capabilities = ["build", "filesystem", "threads"]

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

`config` selects a runtime driver (`sqlite` by default) and database path
(`:memory:` by default). `connect` returns a shared dbkit `connection`; the
concrete SQLx `SqliteConnection` stays private. `available-drivers` currently
reports only `sqlite`; `postgres` and `mysql` are recognized but unavailable,
and unknown driver names fail without a fallback. SQLx 0.9 provides the local
SQLite runtime; remote drivers, a database-shaped Rust facade, pool, ORM, query
builder, migration framework, and streaming cursor are not provided. Future
drivers are not promised SQL portability.

`prepare` genuinely prepares SQL through SQLx's connection-bound `prepare_with`.
dbkit retains owned SQL metadata and reusable bindings, not an independent native
statement handle. A fixed schema-refresh operation runs before native work,
cached metadata is cleared before preparation, and execution uses non-persistent
SQLx queries to avoid SQLx 0.9's schema-change column-cache panic. This currently
sacrifices compiled execution-cache reuse, not public statement reuse. Coordinate
concurrent schema migrations with active queries. See the manual for the
conditions for restoring persistence.
Use `bind` to assign a value using a name without `:`, and
`clear-bindings` to clear assignments. Rebinding replaces the previous value.
Repeated `:name` placeholders are accepted and each occurrence uses the same
binding; every occurrence must have a binding before execution. Binding an
unknown name fails, so surplus names are rejected. Only `:name` placeholders
are supported; positional `?`, `@name`, `$name`, and PostgreSQL `::` casts
are unsupported. Only one SQL statement may be supplied. The parser has SQLite
quote/comment awareness, but is not a general dialect parser; see the API
manual for exact current limits.

Each current typed Rust boundary is narrow and specific: `checked-sql` builds
SQLx's safe SQL wrapper from a source string reference; `statement-sql` reads
owned prepared SQL text for `query_with`; `statement-columns` and `row-columns`
copy column names; `read-row-value` performs checked ordinal access, with
`row-value` translating failure to a dbkit error; `value-kind` copies the native
storage-class name; and `transaction-state` reads autocommit from the SQLx locked
handle using `unsafe rust` and `sqlite3_get_autocommit`. The lock makes access
safe. Retire each bridge when projected safe SQL construction, owned metadata,
borrowed column names, checked `usize` conversion, storage-class name access,
or locked-handle autocommit inspection can express its exact boundary.

Transaction state is read from SQLite's autocommit flag while the SQLx
connection's locked handle is held; this reflects raw transaction SQL and
implicit rollback that SQLx transaction depth does not track. Do not infer
transaction state from a separate counter. During ordinary live operations this
inspection occurs while the connection is acquired; cancellation cleanup must
restore ownership synchronously and must not await the native locked handle.
After cancellation, `in-transaction` reports `transaction-state-unknown` until
another live operation refreshes state, rather than returning a stale boolean.

Database values preserve SQLite storage classes (null, int64 integer, float64
real, text, bytes); booleans bind as integer 1/0 and read back as integers.
Accessors are strict; there is no implicit conversion. Query results are fully
buffered; exhaustion returns `none`, distinct from a row containing SQL NULL.
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
target/release/terrane run packages/dbkit/examples/http -- 127.0.0.1:3000
```

The Python suite uses only the standard library. It builds its native fixture
once, exercises error/reuse/value/lifetime scenarios, and independently checks
file persistence and abandoned-transaction rollback using Python's SQLite client.
The HTTP example prints its bound URL; `GET /notes` reads seeded data through dbkit.
