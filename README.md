# dittoctl

A command line tool for [Eclipse Ditto](https://eclipse.dev/ditto/): inspect things, policies and connections; search with RQL and
export the results; run bulk modifications and message invocations safely; watch change streams; run DevOps commands.

> Status: early development (milestones M0–M4 done). See [PLAN.md](PLAN.md) for the roadmap and
> [docs/reference.md](docs/reference.md) for all commands and options.

## Install

Requires Python 3.11+.

```shell
pipx install dittoctl          # or: uv tool install dittoctl
```

From a checkout:

```shell
python3 -m venv .venv && .venv/bin/pip install -e . --group dev
```

## Quick start

Create a context for a Ditto instance and log in:

```shell
# Ditto's docker-compose setup with nginx basic auth
dittoctl config add-context local --url http://localhost:8080 --auth basic --username ditto
dittoctl auth login                # prompts for the password, stores it in the OS keyring

# an OIDC provider, logging in with the browser (authorization code + PKCE)
dittoctl config add-context prod --url https://ditto.example.com --protected \
  --auth oidc --issuer https://idp.example.com/realms/iot --client-id dittoctl --scope openid --scope offline_access
dittoctl --context prod auth login
```

Then:

```shell
dittoctl whoami                                # subjects Ditto derives from your credentials
dittoctl api GET /api/2/things/org.example:sensor-1
dittoctl api PATCH /api/2/things/org.example:sensor-1/attributes -d '{"location":"lab"}' --if-equal skip
dittoctl -v api GET /api/2/whoami              # also prints the request as a curl command (token redacted)
```

Without a context, `--url` plus `DITTOCTL_TOKEN` (or `DITTOCTL_USERNAME`/`DITTOCTL_PASSWORD`) is enough, which suits CI jobs.

## Reading things

```shell
dittoctl things get org.example:sensor-1                         # whole thing as JSON
dittoctl things get org.example:sensor-1 --path attributes/location --at-revision 42
dittoctl things count -f 'exists(features/temp)'
dittoctl things fields -n org.example --path attributes          # which paths exist, with types and examples
dittoctl things search -f 'gt(_modified,"2026-11-01T00:00:00Z")' --sort -_modified --limit 20 -o table
dittoctl things search -n org.example -o ids > ids.txt           # one thing id per line, for piping
dittoctl things export -f @filter.rql --fields thingId,attributes,features/temp/properties --out temp.csv --excel
dittoctl things watch -n org.example                             # live changes as NDJSON, Ctrl+C to stop
dittoctl things watch --ids org.example:sensor-1 --max-events 1 --duration 2m   # wait for the next change
```

`things fields` inspects the first `--sample` matching things (default 100) and lists every path with its JSON
types, how many things have it and a few example values: what to filter on and which fields to select, also for
things without a WoT model.

Searches follow Ditto's result cursor through all pages. Long filters are sent as a form-encoded POST, so URL
length limits don't apply. `export` streams: memory use stays flat no matter how many things are exported.

When only thing ids are needed (`-o ids`), dittoctl uses Ditto's SSE search stream instead: one request, about
twice as fast and cheaper for Ditto. As soon as other fields are selected, paging is about 4x faster and cheaper,
because Ditto retrieves each streamed thing with its own command. `--transport paging|sse` overrides the choice.
If a Ditto gateway throttles SSE search (`GATEWAY_SSE_THROTTLING_*`), turn the automatic streaming off for that
context with `config add-context ... --no-search-streaming`.

Output formats (`-o`): `table` (default on a terminal), `ndjson` (default when piped), `json`, `csv`, `ids`.
For CSV, nested JSON is flattened into `/`-separated columns, discovered from the first 100 rows
(`--discover-rows N`, `0` for all rows) or set explicitly with `--columns`. `--short-headers` shortens the column
names, `--excel` writes a UTF-8 BOM and Excel-friendly timestamps.
On a terminal, JSON and NDJSON output is syntax-highlighted (`NO_COLOR=1` turns colors off); piped output and
files are plain.

## Changing things

Write commands act on a selection: thing ids as arguments, `--ids-file FILE` (or `-` for stdin), or
`-f/--filter RQL` (with `-n` namespaces), optionally narrowed with `--include-file`/`--exclude-file`.

```shell
dittoctl things set attributes/location/room lab org.example:sensor-1
dittoctl things patch features/config/properties -d '{"interval":60}' -f 'eq(attributes/model,"X1")' --dry-run
dittoctl things array add attributes/tags --items '["maintenance"]' --as-set -f 'eq(attributes/building,"B1")'
dittoctl things unset attributes/obsolete -f 'exists(attributes/obsolete)'
dittoctl things verify features/config/properties/interval --equals 60 -f 'eq(attributes/model,"X1")'
dittoctl things delete -f 'eq(attributes/decommissioned,true)' --yes
dittoctl things import backup.ndjson                 # create things from an NDJSON export
dittoctl things edit org.example:sensor-1            # in $EDITOR, written back with If-Match
dittoctl things diff org.example:sensor-1 --file sensor-1.json
dittoctl messages send reboot -f 'eq(attributes/firmware,"1.2.0")' --timeout 0
```

Safety:

- `--dry-run` shows what would be sent, without writing anything.
- Above `--max-affected` things (default 100) `--yes` is required.
- Deleting asks for confirmation, or needs `--yes` when not interactive.
- Contexts created with `--protected` require typing the context name, or `--confirm-context NAME`, for every
  command that writes (also single writes such as `policies put`, and `api` with a writing method).
- Merge writes on the whole thing (`set`, `unset`, `patch /`) send `If-Match: *`: a thing that doesn't exist is
  reported as `not-found` rather than created by Ditto.
- Bulk writes send `If-Equal: skip`, so re-running a command doesn't change anything that is already right.
- Array changes are read-modify-write with `If-Match`, so concurrent changes are never lost.
- A merge patch containing an array is refused, because it would replace the whole array (`--replace-array`
  allows it).

Bulk runs use `--concurrency` (default 8) parallel requests, optionally limited by `--rate N` per second, and print
a summary per result: `ok`, `unchanged`, `condition-not-met`, `exists`, `conflict`, `not-found`, `failed`.
`--failed-out FILE` lists the failed things; the file can be passed back as `--ids-file` to retry them.
`--journal FILE` records finished things, so that a run interrupted with Ctrl+C continues with `--resume`.
`--results failures|all` prints a JSON line per thing on stdout (failures with Ditto's error and its description),
then a summary line. Exit code 2 means some things failed.

## Policies

```shell
dittoctl policies get org.example:policy-1 --resolved            # with imported entries (Ditto 3.9+)
dittoctl policies entries list org.example:policy-1
dittoctl policies subjects add org.example:policy-1 users nginx:alice --expiring-at 2027-01-01T00:00:00Z
dittoctl policies imports add org.example:policy-1 org.example:shared-policy
dittoctl policies check org.example:sensor-1 --resource thing:/attributes --permission WRITE
dittoctl policies list -f 'like(policyId,"org.example:customer-*")'      # policies of the matching things
```

`policies subjects migrate` adds a new subject next to (or, with `--remove-old`, instead of) every subject matching
a regular expression, with the same permissions and expiry. That's useful when switching identity providers.
Each policy is written atomically with `If-Match`, re-running is safe, and the bulk options (`--dry-run`,
`--journal`, ...) apply:

```shell
dittoctl policies subjects migrate -f 'like(policyId,"org.example:customer-*")' \
    --match 'oldidp:(?P<sub>[0-9a-f-]{36})' --template 'newidp:fed-sub:\g<sub>' --dry-run
```

## Connections

Ditto's connections API usually requires its DevOps login, so use a separate context for it:

```shell
dittoctl config add-context prod-devops --url https://ditto.example.com --auth basic --username devops
dittoctl -c prod-devops connections list                          # URIs without passwords
dittoctl -c prod-devops connections test -d @mqtt-connection.json # connects once, creates nothing
dittoctl -c prod-devops connections put my-mqtt -d @mqtt-connection.json
dittoctl -c prod-devops connections status my-mqtt
dittoctl -c prod-devops connections logs my-mqtt --enable --follow
```

Ditto's connection log messages include the headers of the request that caused a message, including
`Authorization`. dittoctl masks those values and URI passwords unless `--no-redact` is given.

## Live channel and paged messages

```shell
# ask the device instead of the twin; fall back to the twin if it doesn't answer within 3s
dittoctl things get org.example:sensor-1 --path features --live --live-timeout 3 --live-timeout-strategy use-twin
# devices answering in pages: re-send while the answer contains "next", passing it on as "token"
dittoctl messages send history org.example:sensor-1 -d '{"from":"2026-11-01"}' --paginate next:token
dittoctl messages claim org.example:sensor-1
```

## History

With history retention configured in Ditto, earlier states of a thing can be read and streamed:

```shell
dittoctl things get org.example:sensor-1 --at-revision 42
dittoctl things get org.example:sensor-1 --at-time 2026-11-01T12:00:00Z
dittoctl things history org.example:sensor-1 --from-revision -10           # the last ten changes, as NDJSON
dittoctl things history org.example:sensor-1 --from-time 2026-11-01T00:00:00Z --to-time 2026-11-02T00:00:00Z
```

## Web of Things

```shell
dittoctl things create org.example:lamp-1 --definition https://models.example.org/lamp-1.0.0.tm.jsonld
dittoctl things td org.example:lamp-1                      # the Thing Description Ditto generates
dittoctl things td org.example:lamp-1 --with-features --compact   # all features, in a compact form
dittoctl things migrate-definition --definition https://models.example.org/lamp-2.0.0.tm.jsonld \
    --init-defaults -f 'eq(definition,"https://models.example.org/lamp-1.0.0.tm.jsonld")' --dry-run
dittoctl wot directory                                     # Ditto's Thing Directory (3.9+)
```

`migrate-definition --dry-run` lets Ditto compute the migration without applying it.

`td --with-features` returns a thing's Thing Description together with those of all its features, in one
call. `--compact` leaves out what follows from Ditto's conventions: forms, security and error schemas. It
keeps titles, descriptions, data schemas, units and semantic types, plus the Ditto path of every property,
action and event. Features with the same description are listed once (`{"sameAs": "<feature>"}`), and so are
repeated data schemas (`{"$ref": "#/<JSON pointer>"}`). That makes it 7 to 12 times smaller for small models and
about 2.5 times for large real-world ones, which makes it a good way to tell an LLM agent what a thing offers.
`--no-schema-descriptions` also leaves out the descriptions inside data schemas, for another 20 to 25%.

## DevOps

Like connections, these commands need Ditto's DevOps login:

```shell
dittoctl -c prod-devops devops status --health
dittoctl -c prod-devops devops logging set org.eclipse.ditto debug --service things
dittoctl -c prod-devops devops config gateway --path ditto.gateway.streaming
dittoctl -c prod-devops devops reindex -n org.example         # rebuild the search index of a namespace
dittoctl -c prod-devops devops piggyback things -d @command.json
dittoctl -c prod-devops devops namespace erase org.example.old   # block, shut down, purge, unblock
```

## RQL

Filters are checked locally before they're sent, and errors point at the position:

```shell
$ dittoctl rql lint 'and(eq(attributes/room,lab),exists(features/temp))'
Error: invalid RQL: expected a value: a quoted string, a number, true, false or null (strings need quotes) (at position 23)
  and(eq(attributes/room,lab),exists(features/temp))
                         ^
$ dittoctl rql fmt 'and(eq(attributes/room,"lab"),exists(features/temp))'
and(
  eq(attributes/room,"lab"),
  exists(features/temp)
)
```

Filters may be written over several lines (e.g. in a file passed as `-f @filter.rql`); dittoctl removes the
whitespace before sending them.

## Authentication

| Method    | Settings                                       | Credentials                                                         |
|-----------|------------------------------------------------|---------------------------------------------------------------------|
| `none`    |                                                |                                                                     |
| `basic`   | `--username`                                   | password via `auth login`, or `DITTOCTL_PASSWORD`                   |
| `token`   |                                                | bearer token via `auth login`, or `DITTOCTL_TOKEN`                  |
| `preauth` | `--subject`, e.g. `nginx:ditto`                | none; sends the `x-ditto-pre-authenticated` header                  |
| `oidc`    | `--issuer`, `--client-id`, `--flow`, `--scope` | `auth login` runs the `pkce`, `device` or `client-credentials` flow |

Secrets are stored in the OS keyring. Where no keyring is available they go to a file readable only by you
(`~/.local/state/dittoctl/secrets.json`). Set `DITTOCTL_SECRET_STORE=keyring|file` to choose explicitly.
The config file (`~/.config/dittoctl/config.toml`) never contains secrets.

## Conditional requests

Ditto's conditional headers are first-class options on write commands:

| Option                                           | Ditto header / parameter       |
|--------------------------------------------------|--------------------------------|
| `--if-match ETAG\|*`                             | `If-Match`                     |
| `--if-none-match ETAG\|*`                        | `If-None-Match`                |
| `--if-equal update\|skip\|skip-minimizing-merge` | `If-Equal`                     |
| `--condition RQL`                                | `condition`                    |
| `--patch-condition PATH=RQL`                     | `merge-thing-patch-conditions` |
| `--live-condition RQL`                           | `live-channel-condition`       |

## Shell completion

```shell
eval "$(dittoctl completion zsh)"     # or bash; fish: dittoctl completion fish | source
```

## Use by AI agents

dittoctl detects AI coding agents such as Claude Code (by the `CLAUDECODE` or `AI_AGENT` environment variables)
and then adapts its output; `--agent`/`--no-agent` or `DITTOCTL_AGENT=1|0` set it explicitly:

- JSON on stdout is a single line, and errors are one JSON line on stderr: `exitCode`, `message`, and for Ditto
  errors `status`, `error`, `description`, `correlationId`; usage errors include the usage line.
- `things search`, `export` (to stdout), `history` and `policies list` show the first 50 results and say so on
  stderr if there are more; `--limit N` or `--all` override that.
- `things watch` and `connections logs --follow` stop after 30 seconds unless `--duration` (`0` for no limit) or
  `--max-events` is given.
- Bulk writes print `--results failures`: a JSON line per failed thing, then a summary line. In a dry run, these
  are the first planned requests.
- `things diff` prints a JSON list of changes.
- Writes to protected contexts are refused: a person should run those.

Two commands tell an agent what it can work with: `things fields` (the paths and types of real things) and
`things td --with-features --compact` (the WoT Thing Description of modelled things, 2 to 12 times smaller).

## Exit codes

| Code | Meaning                                                                                               |
|------|-------------------------------------------------------------------------------------------------------|
| 0    | success                                                                                               |
| 1    | usage error or failed request                                                                         |
| 2    | partial failure of a bulk operation                                                                   |
| 3    | authentication failed                                                                                 |
| 4    | not found                                                                                             |
| 5    | aborted (e.g. by a safety check)                                                                      |
| 6    | a check failed: differences (`diff`), mismatches (`verify`), denied permissions, invalid RQL (`lint`) |

## Development

```shell
.venv/bin/pytest
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/python scripts/gen_reference.py      # after changing commands or help texts (a test checks it)
```

## Contributing

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).
Please report vulnerabilities as described in [SECURITY.md](SECURITY.md), not in public issues.

## License

[Eclipse Public License 2.0](https://www.eclipse.org/legal/epl-2.0/). dittoctl was largely created with the
assistance of an AI; the AI-generated portions are made available under
[CC0-1.0](legal/CC0-1.0.txt), as described in [NOTICE.md](NOTICE.md).
