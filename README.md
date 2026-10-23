# dbkit

dbkit is a Terrane-native relational-database toolkit. It is not Terrane's
canonical database layer; it starts with SQLite and is intended to grow backend
modules for Postgres and MySQL.

`open` returns a dbkit `connection`, not SQLx's `SqliteConnection`. The native
connection is an implementation detail held inside the backend-specific dbkit
connection object. Applications keep and pass the dbkit connection; dbkit owns how
its native resource is borrowed, closed, and destroyed.

```terrane
from /terrane/dbkit/sqlite import config, open

database = await open; (instance config; 'application.db', true)
# use database through dbkit operations
await database.close;
```

`connection.close` is idempotent and asynchronously closes the internal native
connection. The connection destructor delegates to the same close operation: if an
application lets a still-open dbkit connection end its lifetime, destruction waits
for SQLx close to complete. The application never needs the raw SQLx connection to
release its resource.

## Current scope

`config`, opaque `connection` creation through `open`, and explicit `close` are
implemented and verified. The package contains no Rust.

Statement execution and result fetching are intentionally not public yet. The
required design is one stable dbkit connection that can execute repeatedly and be
passed by reference to other application code. The direct projected SQLx surface
currently cannot receive that dbkit-owned resource through the native-call boundary:
see `docs/dump/dbkit-issue.md` for the concrete compiler repro and design notes.

## Verify

```console
terrane test packages/dbkit
terrane run packages/dbkit/examples/basic
```
