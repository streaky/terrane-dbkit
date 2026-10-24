# dbkit HTTP example

This application seeds a file-backed SQLite database once at startup, then serves its first note through the HTTP-server annotated-route consumer. Each request opens and closes its own connection to the same database file, so simultaneous requests do not compete for a single dbkit connection lease. The file defaults to `packages/dbkit/examples/http/notes.sqlite` relative to the repository root; pass a second run argument to select another path. Its parent directory must already exist.

From the repository root, build and run it with a current Terrane compiler:

```sh
terrane build packages/dbkit/examples/http
terrane run packages/dbkit/examples/http -- 127.0.0.1:0 packages/dbkit/examples/http/notes.sqlite
```

The program binds `127.0.0.1:0` by default and prints the actual selected URL, for example `Notes API: http://127.0.0.1:49152/notes`. Copy that URL into curl:

```sh
curl http://127.0.0.1:<printed-port>/notes
```

The response body is `hello from dbkit`. Pass a fixed address as the first run argument (for example `127.0.0.1:3000`) to select a known port; pass a database path as the second argument. Each handler explicitly closes its statement and per-request connection. This example uses no pool or request queue. Separate connections avoid dbkit's shared-connection `connection-busy` behavior, but SQLite locking can still occur for concurrent writes; SQLx's default `busy_timeout=5000` waits up to five seconds. The route only reads. The example requires native package/consumer support, SQLite filesystem/thread capabilities, and the HTTP-server's networking capabilities.
