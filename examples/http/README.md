# dbkit HTTP example

This small application seeds an in-memory SQLite database, then serves its first note through the HTTP-server annotated-route consumer.

From the repository root, build and run it with a current Terrane compiler:

```sh
terrane build packages/dbkit/examples/http
terrane run packages/dbkit/examples/http -- 127.0.0.1:0
```

The program binds `127.0.0.1:0` by default and prints the actual selected URL, for example `Notes API: http://127.0.0.1:49152/notes`. Copy that URL into curl:

curl http://127.0.0.1:<printed-port>/notes

The response body is `hello from dbkit`. Pass a fixed address as the run argument (for example `127.0.0.1:3000`) to select a known port. The example requires native package/consumer support, SQLite filesystem/thread capabilities, and the HTTP-server's networking capabilities.
