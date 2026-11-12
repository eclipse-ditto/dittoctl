# Command reference

Generated from the commands' help texts by `scripts/gen_reference.py`; don't edit by hand.

## `dittoctl`

```text
Usage: dittoctl [OPTIONS] COMMAND [ARGS]...

  dittoctl - command line tool for Eclipse Ditto.

Options:
  -V, --version            Show the version and exit.
  -c, --context TEXT       Context to use instead of the current one. [env: DITTOCTL_CONTEXT]
  --url TEXT               Ditto base URL. Without --context, credentials come from DITTOCTL_TOKEN
                           or DITTOCTL_USERNAME/DITTOCTL_PASSWORD. [env: DITTOCTL_URL]
  -H, --header NAME:VALUE  Extra request header. Repeatable.
  --timeout FLOAT          Request timeout in seconds.
  --correlation-id TEXT    Prefix for the correlation-id of each request (default: random per run).
  -v, --verbose            -v prints requests as curl commands, -vv also response headers.
  --config FILE            Config file. [env: DITTOCTL_CONFIG]
  --agent / --no-agent     Output for AI agents: single-line JSON, errors as JSON, limited result
                           sizes, per-thing results of bulk writes, no writes to protected contexts.
                           Default: on if CLAUDECODE or AI_AGENT is set. [env: DITTOCTL_AGENT]
  -h, --help               Show this message and exit.

Commands:
  api          Send an authenticated request to any Ditto endpoint and print the response.
  auth         Log in to the current context and manage its credentials.
  completion   Print the shell completion script.
  config       Manage contexts: named Ditto endpoints with their authentication settings.
  connections  Manage connections (usually needs Ditto's DevOps login: use a separate context).
  devops       Operate Ditto: log levels, configuration, piggyback commands, reindexing,...
  messages     Send messages to things and their features, for example commands for devices.
  policies     Read and change policies: entries, subjects, imports; check permissions; migrate...
  rql          Check and format RQL filter expressions, without contacting Ditto.
  things       Read, search, count, export and watch things.
  whoami       Show the subjects Ditto derives from your credentials.
  wot          Web of Things (WoT): Ditto's Thing Directory.
```

### `dittoctl api`

```text
Usage: dittoctl api [OPTIONS] METHOD PATH

  Send an authenticated request to any Ditto endpoint and print the response.

  Examples:
    dittoctl api GET /api/2/whoami
    dittoctl api GET /api/2/things/org.example:sensor-1 -q fields=thingId,attributes
    dittoctl api PATCH /api/2/things/org.example:sensor-1/attributes -d '{"location":"lab"}' --if-equal skip
    dittoctl api PUT /api/2/things/org.example:sensor-2 -d @thing.json --if-none-match '*'

Options:
  -d, --data TEXT                 Request body: inline, @file, or @- for stdin.
  -q, --query NAME=VALUE          Query parameter. Repeatable.
  --content-type TEXT             Content type of the body (default: derived from method and body).
  -i, --include                   Print the response status and headers to stderr.
  -o, --output [json|ndjson|raw]  Output format.  [default: json]
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  -h, --help                      Show this message and exit.
```

### `dittoctl auth`

```text
Usage: dittoctl auth [OPTIONS] COMMAND [ARGS]...

  Log in to the current context and manage its credentials.

Options:
  -h, --help  Show this message and exit.

Commands:
  login   Obtain credentials and store them in the OS keyring.
  logout  Delete the stored credentials of the current context.
  status  Show how the current context authenticates and whether credentials are available.
  token   Print a valid bearer token, for example to paste into the Ditto UI or use with curl.
```

#### `dittoctl auth login`

```text
Usage: dittoctl auth login [OPTIONS]

  Obtain credentials and store them in the OS keyring.

  basic   prompts for the password (or reads it with --password-stdin)
  token   prompts for the token (or reads it with --token-stdin)
  oidc    runs the configured flow: browser login (pkce), device code (device),
          or client credentials (with the client secret from --secret-stdin)

Options:
  --password-stdin  [basic] Read the password from stdin.
  --token-stdin     [token] Read the bearer token from stdin.
  --secret-stdin    [oidc] Read the client secret from stdin.
  --no-browser      [oidc pkce] Print the login URL instead of opening a browser.
  -h, --help        Show this message and exit.
```

#### `dittoctl auth logout`

```text
Usage: dittoctl auth logout [OPTIONS]

  Delete the stored credentials of the current context.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl auth status`

```text
Usage: dittoctl auth status [OPTIONS]

  Show how the current context authenticates and whether credentials are available.

Options:
  -o, --output [text|json]  Output format.  [default: text]
  -h, --help                Show this message and exit.
```

#### `dittoctl auth token`

```text
Usage: dittoctl auth token [OPTIONS]

  Print a valid bearer token, for example to paste into the Ditto UI or use with curl.

Options:
  -h, --help  Show this message and exit.
```

### `dittoctl completion`

```text
Usage: dittoctl completion [OPTIONS] {bash|zsh|fish}

  Print the shell completion script.

  bash:  eval "$(dittoctl completion bash)"
  zsh:   eval "$(dittoctl completion zsh)"
  fish:  dittoctl completion fish | source

Options:
  -h, --help  Show this message and exit.
```

### `dittoctl config`

```text
Usage: dittoctl config [OPTIONS] COMMAND [ARGS]...

  Manage contexts: named Ditto endpoints with their authentication settings.

Options:
  -h, --help  Show this message and exit.

Commands:
  add-context      Add a context.
  current-context  Print the name of the current context.
  delete-context   Delete a context and its stored credentials.
  get-contexts     List all contexts.
  path             Print the path of the config file.
  use-context      Select the context used when --context is not given.
  view             Print the configuration, or a single context, as TOML.
```

#### `dittoctl config add-context`

```text
Usage: dittoctl config add-context [OPTIONS] NAME

  Add a context.

Options:
  --url TEXT                      Base URL of Ditto, e.g. https://ditto.example.com  [required]
  --auth [none|basic|token|preauth|oidc]
                                  How to authenticate; the options below marked [method] configure
                                  it.  [default: none]
  --username TEXT                 [basic] User name.
  --subject TEXT                  [preauth] Value of the x-ditto-pre-authenticated header, e.g.
                                  nginx:ditto.
  --issuer TEXT                   [oidc] Issuer URL used for discovery.
  --client-id TEXT                [oidc] OAuth2 client id.
  --flow [pkce|device|client-credentials]
                                  [oidc] Login flow.  [default: pkce]
  --scope TEXT                    [oidc] Scope to request; repeatable. Default: openid.
  --auth-param NAME=VALUE         [oidc] Extra parameter for the authorization request, e.g.
                                  audience=ditto. Repeatable.
  --redirect-port INTEGER         [oidc] Fixed loopback port for the PKCE redirect (default:
                                  random).
  --use-id-token                  [oidc] Send the id token to Ditto instead of the access token.
  --namespace TEXT                Default namespace for searches. Repeatable.
  --header NAME=VALUE             Header sent with every request.
  --protected                     Require typing the context name to confirm writes (e.g.
                                  production).
  --timeout FLOAT                 Request timeout in seconds.  [default: 30.0]
  --ca-cert FILE                  CA bundle to verify TLS with.
  --insecure                      Don't verify TLS certificates.
  --no-search-streaming           Never stream searches via SSE automatically, e.g. if the Ditto
                                  gateway throttles SSE search.
  --use / --no-use                Make it the current context (default: if it's the first).
  --overwrite                     Replace an existing context with the same name.
  -h, --help                      Show this message and exit.
```

#### `dittoctl config current-context`

```text
Usage: dittoctl config current-context [OPTIONS]

  Print the name of the current context.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl config delete-context`

```text
Usage: dittoctl config delete-context [OPTIONS] NAME

  Delete a context and its stored credentials.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl config get-contexts`

```text
Usage: dittoctl config get-contexts [OPTIONS]

  List all contexts.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl config path`

```text
Usage: dittoctl config path [OPTIONS]

  Print the path of the config file.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl config use-context`

```text
Usage: dittoctl config use-context [OPTIONS] NAME

  Select the context used when --context is not given.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl config view`

```text
Usage: dittoctl config view [OPTIONS] [NAME]

  Print the configuration, or a single context, as TOML.

Options:
  -h, --help  Show this message and exit.
```

### `dittoctl connections`

```text
Usage: dittoctl connections [OPTIONS] COMMAND [ARGS]...

  Manage connections (usually needs Ditto's DevOps login: use a separate context).

Options:
  -h, --help  Show this message and exit.

Commands:
  close          Close a connection.
  create         Create a connection; fails if it exists.
  delete         Delete a connection.
  get            Retrieve a connection's configuration.
  list           List all connections.
  logs           Show a connection's logs: successful and failed messages per source/target...
  metrics        Show a connection's message metrics.
  open           Open a connection.
  put            Create or replace a connection with the given id.
  reset-metrics  Reset a connection's metrics.
  status         Show the live status of a connection, its clients, sources and targets.
  test           Check a connection configuration (Ditto connects once, then discards it;...
```

#### `dittoctl connections close`

```text
Usage: dittoctl connections close [OPTIONS] CONNECTION_ID

  Close a connection.

Options:
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl connections create`

```text
Usage: dittoctl connections create [OPTIONS]

  Create a connection; fails if it exists. Without an "id" in the JSON, Ditto generates one.

  See 'connections test' to check a connection without creating it.

Options:
  -d, --data JSON|@FILE|@-  The connection JSON.  [required]
  --confirm-context NAME    Confirm a protected context without the prompt (for scripts).
  -h, --help                Show this message and exit.
```

#### `dittoctl connections delete`

```text
Usage: dittoctl connections delete [OPTIONS] CONNECTION_ID

  Delete a connection.

Options:
  -y, --yes               Don't ask for confirmation.
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl connections get`

```text
Usage: dittoctl connections get [OPTIONS] CONNECTION_ID

  Retrieve a connection's configuration.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl connections list`

```text
Usage: dittoctl connections list [OPTIONS]

  List all connections. URIs are shown without passwords.

Options:
  -o, --output [table|json|ids]  Output format.  [default: table]
  -h, --help                     Show this message and exit.
```

#### `dittoctl connections logs`

```text
Usage: dittoctl connections logs [OPTIONS] CONNECTION_ID

  Show a connection's logs: successful and failed messages per source/target address.

  Ditto's log messages contain the headers of the request that caused a message, including
  Authorization headers; dittoctl masks them unless --no-redact is given. The table shortens long
  messages; -o ndjson shows them completely.

  Example:
    dittoctl connections logs my-connection --enable --follow -o ndjson

Options:
  --enable                     Enable logging first (Ditto keeps it on for a limited time).
  --reset                      Clear the logs first.
  --follow                     Keep polling and print new entries as they appear, until Ctrl+C or
                               --duration.
  --interval FLOAT             Seconds between polls with --follow.  [default: 2.0]
  --duration DURATION          Stop following after this long, e.g. 30s or 5m; 0 never stops
                               (default; agent mode: 30s).
  --no-redact                  Show Authorization headers and URI passwords in log messages.
  -o, --output [table|ndjson]  Output format.  [default: table]
  --confirm-context NAME       Confirm a protected context without the prompt (for scripts).
  -h, --help                   Show this message and exit.
```

#### `dittoctl connections metrics`

```text
Usage: dittoctl connections metrics [OPTIONS] CONNECTION_ID

  Show a connection's message metrics.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl connections open`

```text
Usage: dittoctl connections open [OPTIONS] CONNECTION_ID

  Open a connection.

Options:
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl connections put`

```text
Usage: dittoctl connections put [OPTIONS] CONNECTION_ID

  Create or replace a connection with the given id.

Options:
  -d, --data JSON|@FILE|@-  The connection JSON.  [required]
  --confirm-context NAME    Confirm a protected context without the prompt (for scripts).
  -h, --help                Show this message and exit.
```

#### `dittoctl connections reset-metrics`

```text
Usage: dittoctl connections reset-metrics [OPTIONS] CONNECTION_ID

  Reset a connection's metrics.

Options:
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl connections status`

```text
Usage: dittoctl connections status [OPTIONS] CONNECTION_ID

  Show the live status of a connection, its clients, sources and targets.

Options:
  -o, --output [table|json]  Output format.  [default: table]
  -h, --help                 Show this message and exit.
```

#### `dittoctl connections test`

```text
Usage: dittoctl connections test [OPTIONS]

  Check a connection configuration (Ditto connects once, then discards it; nothing is created).

Options:
  -d, --data JSON|@FILE|@-  The connection JSON to test.  [required]
  -h, --help                Show this message and exit.
```

### `dittoctl devops`

```text
Usage: dittoctl devops [OPTIONS] COMMAND [ARGS]...

  Operate Ditto: log levels, configuration, piggyback commands, reindexing, namespaces, status.

  These endpoints need Ditto's DevOps login; use a separate context, e.g. 'dittoctl -c prod-devops
  devops ...'.

Options:
  -h, --help  Show this message and exit.

Commands:
  config     Show the runtime configuration of services (large: narrow it down with --path).
  logging    Show and change log levels at runtime.
  namespace  Namespace operations.
  piggyback  Send a piggyback command to actors in the Ditto cluster (SERVICE: things, search,...
  reindex    Rebuild search index entries: of single things immediately, or of all things (or...
  status     Show the Ditto version and gateway status, optionally with the cluster health.
```

#### `dittoctl devops config`

```text
Usage: dittoctl devops config [OPTIONS] [gateway|things|things-search|policies|connectivity]

  Show the runtime configuration of services (large: narrow it down with --path).

Options:
  --instance TEXT  Only this instance of the service.
  --path TEXT      Only this part of the configuration, e.g. ditto.gateway.streaming.
  -h, --help       Show this message and exit.
```

#### `dittoctl devops logging`

```text
Usage: dittoctl devops logging [OPTIONS] COMMAND [ARGS]...

  Show and change log levels at runtime.

Options:
  -h, --help  Show this message and exit.

Commands:
  get  Show the log levels of all services, or of one.
  set  Set the level of a logger, such as 'org.eclipse.ditto debug'.
```

#### `dittoctl devops logging get`

```text
Usage: dittoctl devops logging get [OPTIONS] [gateway|things|things-search|policies|connectivity]

  Show the log levels of all services, or of one.

Options:
  -o, --output [table|json]  Output format.  [default: table]
  -h, --help                 Show this message and exit.
```

#### `dittoctl devops logging set`

```text
Usage: dittoctl devops logging set [OPTIONS] LOGGER {trace|debug|info|warn|error|off}

  Set the level of a logger, such as 'org.eclipse.ditto debug'. Takes effect immediately, until a
  restart.

Options:
  --service [gateway|things|things-search|policies|connectivity]
                                  Only this service (default: all).
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  -h, --help                      Show this message and exit.
```

#### `dittoctl devops namespace`

```text
Usage: dittoctl devops namespace [OPTIONS] COMMAND [ARGS]...

  Namespace operations.

Options:
  -h, --help  Show this message and exit.

Commands:
  erase  Erase ALL data of a namespace: things, policies, connections' data and search index...
```

#### `dittoctl devops namespace erase`

```text
Usage: dittoctl devops namespace erase [OPTIONS] NAMESPACE

  Erase ALL data of a namespace: things, policies, connections' data and search index entries.

  Runs Ditto's documented sequence: block the namespace, shut down its actors, purge its data from
  the persistence, unblock it. Cannot be undone.

Options:
  --confirm-namespace NAMESPACE  Confirm without the prompt (for scripts).
  --purge-timeout TEXT           How long Ditto waits for the services to confirm the erasure.
                                 [default: 10s]
  --confirm-context NAME         Confirm a protected context without the prompt (for scripts).
  -h, --help                     Show this message and exit.
```

#### `dittoctl devops piggyback`

```text
Usage: dittoctl devops piggyback [OPTIONS] [SERVICE]

  Send a piggyback command to actors in the Ditto cluster (SERVICE: things, search, connectivity,
  ...).

  See https://eclipse.dev/ditto/installation-operating.html#piggyback-commands

Options:
  -d, --data JSON|@FILE|@-  The piggyback command: targetActorSelection, headers, piggybackCommand.
                            [required]
  --instance TEXT           Only this instance of the service.
  --timeout TEXT            How long Ditto waits for responses, e.g. 30s.  [default: 10s]
  --confirm-context NAME    Confirm a protected context without the prompt (for scripts).
  -h, --help                Show this message and exit.
```

#### `dittoctl devops reindex`

```text
Usage: dittoctl devops reindex [OPTIONS]

  Rebuild search index entries: of single things immediately, or of all things (or namespaces) in
  the next background sync. Ditto doesn't report progress; follow the search service's logs.

Options:
  -n, --namespace TEXT    Only things of this namespace. Repeatable.
  --thing THING_ID        Update this thing now. Repeatable.
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl devops status`

```text
Usage: dittoctl devops status [OPTIONS]

  Show the Ditto version and gateway status, optionally with the cluster health.

Options:
  --health                  Also show the health of all cluster members.
  -o, --output [text|json]  Output format.  [default: text]
  -h, --help                Show this message and exit.
```

### `dittoctl messages`

```text
Usage: dittoctl messages [OPTIONS] COMMAND [ARGS]...

  Send messages to things and their features, for example commands for devices.

Options:
  -h, --help  Show this message and exit.

Commands:
  claim  Claim a thing: send a claim message to its inbox, which the device (or a connected...
  send   Send the message SUBJECT to each selected thing and print the responses as NDJSON.
```

#### `dittoctl messages claim`

```text
Usage: dittoctl messages claim [OPTIONS] THING_ID

  Claim a thing: send a claim message to its inbox, which the device (or a connected service)
  answers, for example by granting you access in the thing's policy.

Options:
  --timeout INTEGER RANGE  Seconds to wait for the device's answer.  [default: 10; 0<=x<=60]
  --confirm-context NAME   Confirm a protected context without the prompt (for scripts).
  -h, --help               Show this message and exit.
```

#### `dittoctl messages send`

```text
Usage: dittoctl messages send [OPTIONS] SUBJECT [THING_ID]...

  Send the message SUBJECT to each selected thing and print the responses as NDJSON.

  Each response line has thingId, result, status and response; with --results, failed things get a
  line too.

  Messages are not retried automatically, as devices may not handle duplicates.

  Examples:
    dittoctl messages send reboot org.example:sensor-1 --timeout 0
    dittoctl messages send set-interval -d '{"seconds":60}' --feature config -f 'eq(attributes/model,"X1")'

Options:
  -d, --data JSON|TEXT|@FILE|@-   Message payload; JSON if it parses, else text.
  --content-type TEXT             Content type of the payload (default: application/json, or
                                  text/plain).
  --feature TEXT                  Send to this feature of each thing instead of the thing itself.
  --outbox                        Send from the thing (outbox) instead of to it (inbox).
  --timeout INTEGER RANGE         Seconds to wait for each response; 0 sends without waiting (fire
                                  and forget).  [default: 10; 0<=x<=60]
  --paginate RESPONSE_FIELD[:REQUEST_FIELD]
                                  Follow paged answers: re-send while the response contains
                                  RESPONSE_FIELD, passing its value as REQUEST_FIELD (default: the
                                  same name) in the payload.
  --max-pages INTEGER RANGE       Upper limit of pages per thing with --paginate.  [default: 100;
                                  x>=1]
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

### `dittoctl policies`

```text
Usage: dittoctl policies [OPTIONS] COMMAND [ARGS]...

  Read and change policies: entries, subjects, imports; check permissions; migrate subjects in bulk.

Options:
  -h, --help  Show this message and exit.

Commands:
  activate-token-integration    Add the subject derived from your token to the policy's entries...
  check                         Check which of the given resources of a thing or policy you may...
  deactivate-token-integration  Remove the subject derived from your token from the policy's...
  delete                        Delete a policy.
  entries                       Policy entries: who (subjects) may do what (resources).
  get                           Retrieve a policy.
  imports                       Policy imports: reuse entries of other policies.
  list                          List the distinct policy ids of the things matching a filter.
  put                           Create or completely replace a policy.
  subjects                      Subjects of policy entries: add, remove, and migrate them...
```

#### `dittoctl policies activate-token-integration`

```text
Usage: dittoctl policies activate-token-integration [OPTIONS] POLICY_ID

  Add the subject derived from your token to the policy's entries (needs EXECUTE permission on the
  action and a token-based login; the subject expires with the token).

Options:
  --label TEXT            Only this entry (default: all entries you may execute it on).
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl policies check`

```text
Usage: dittoctl policies check [OPTIONS] ENTITY_ID

  Check which of the given resources of a thing or policy you may access (Ditto 3.7+).

  Exit code 6 if any check is denied.

  Example:
    dittoctl policies check org.example:sensor-1 --resource thing:/attributes --resource thing:/features/temp \
        --permission READ --permission WRITE

Options:
  --resource RESOURCE        E.g. thing:/attributes/location, thing:/features/temp, policy:/,
                             message:/. Repeatable.  [required]
  --permission [READ|WRITE]  Permissions to check. Repeatable.  [default: READ]
  -h, --help                 Show this message and exit.
```

#### `dittoctl policies deactivate-token-integration`

```text
Usage: dittoctl policies deactivate-token-integration [OPTIONS] POLICY_ID

  Remove the subject derived from your token from the policy's entries (needs EXECUTE permission on
  the action and a token-based login; the subject expires with the token).

Options:
  --label TEXT            Only this entry (default: all entries you may execute it on).
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl policies delete`

```text
Usage: dittoctl policies delete [OPTIONS] POLICY_ID

  Delete a policy. Things that still use it become inaccessible.

Options:
  -y, --yes               Don't ask for confirmation.
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl policies entries`

```text
Usage: dittoctl policies entries [OPTIONS] COMMAND [ARGS]...

  Policy entries: who (subjects) may do what (resources).

Options:
  -h, --help  Show this message and exit.

Commands:
  delete  Delete one entry.
  get     Retrieve one entry.
  list    Show the entries of a policy as a table.
  put     Create or replace one entry.
```

#### `dittoctl policies entries delete`

```text
Usage: dittoctl policies entries delete [OPTIONS] POLICY_ID LABEL

  Delete one entry.

Options:
  --allow-lockout         Allow a change that removes your own WRITE permission on the policy (Ditto
                          refuses it otherwise).
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl policies entries get`

```text
Usage: dittoctl policies entries get [OPTIONS] POLICY_ID LABEL

  Retrieve one entry.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl policies entries list`

```text
Usage: dittoctl policies entries list [OPTIONS] POLICY_ID

  Show the entries of a policy as a table.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl policies entries put`

```text
Usage: dittoctl policies entries put [OPTIONS] POLICY_ID LABEL

  Create or replace one entry.

Options:
  -d, --data JSON|@FILE|@-        The entry: subjects and resources.  [required]
  --allow-lockout                 Allow a change that removes your own WRITE permission on the
                                  policy (Ditto refuses it otherwise).
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  -h, --help                      Show this message and exit.
```

#### `dittoctl policies get`

```text
Usage: dittoctl policies get [OPTIONS] POLICY_ID

  Retrieve a policy.

Options:
  --resolved                      Show the effective policy with imports resolved (Ditto 3.9+).
  --path TEXT                     Only this part, e.g. entries/owner or imports.
  -o, --output [json|ndjson]      Output format.  [default: json]
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  -h, --help                      Show this message and exit.
```

#### `dittoctl policies imports`

```text
Usage: dittoctl policies imports [OPTIONS] COMMAND [ARGS]...

  Policy imports: reuse entries of other policies.

Options:
  -h, --help  Show this message and exit.

Commands:
  add     Import the entries of another policy.
  list    Show the imports of a policy.
  remove  Remove an import.
```

#### `dittoctl policies imports add`

```text
Usage: dittoctl policies imports add [OPTIONS] POLICY_ID IMPORTED_POLICY_ID

  Import the entries of another policy.

Options:
  --entry LABEL           Import only this entry (it must be importable). Repeatable; default: all
                          implicit ones.
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl policies imports list`

```text
Usage: dittoctl policies imports list [OPTIONS] POLICY_ID

  Show the imports of a policy.

Options:
  -h, --help  Show this message and exit.
```

#### `dittoctl policies imports remove`

```text
Usage: dittoctl policies imports remove [OPTIONS] POLICY_ID IMPORTED_POLICY_ID

  Remove an import.

Options:
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl policies list`

```text
Usage: dittoctl policies list [OPTIONS]

  List the distinct policy ids of the things matching a filter.

  Ditto can't search policies directly, so they are found via the things using them.

  Example:
    dittoctl policies list -f 'like(policyId,"org.example:customer-*")' > policies.txt

Options:
  -f, --filter RQL          Filter on things; @file reads it.
  --no-validate             Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]  Namespaces of the things.
  --all                     Don't limit the output (agent mode shows the first 50 by default).
  -h, --help                Show this message and exit.
```

#### `dittoctl policies put`

```text
Usage: dittoctl policies put [OPTIONS] POLICY_ID

  Create or completely replace a policy.

Options:
  -d, --data JSON|@FILE|@-        The complete policy JSON.  [required]
  --allow-lockout                 Allow a change that removes your own WRITE permission on the
                                  policy (Ditto refuses it otherwise).
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  -h, --help                      Show this message and exit.
```

#### `dittoctl policies subjects`

```text
Usage: dittoctl policies subjects [OPTIONS] COMMAND [ARGS]...

  Subjects of policy entries: add, remove, and migrate them across many policies.

Options:
  -h, --help  Show this message and exit.

Commands:
  add      Add (or update) a subject of an entry, such as 'integration:my-app' or 'nginx:alice'.
  migrate  Add a new subject next to (or instead of) every subject matching --match, with the...
  remove   Remove a subject from an entry.
```

#### `dittoctl policies subjects add`

```text
Usage: dittoctl policies subjects add [OPTIONS] POLICY_ID LABEL SUBJECT_ID

  Add (or update) a subject of an entry, such as 'integration:my-app' or 'nginx:alice'.

Options:
  --type TEXT              Subject type.  [default: added by dittoctl]
  --expiring-at TIMESTAMP  ISO-8601 time after which Ditto removes the subject.
  --confirm-context NAME   Confirm a protected context without the prompt (for scripts).
  -h, --help               Show this message and exit.
```

#### `dittoctl policies subjects migrate`

```text
Usage: dittoctl policies subjects migrate [OPTIONS] [POLICY_ID]...

  Add a new subject next to (or instead of) every subject matching --match, with the same
  permissions.

  Typical when switching identity providers: users keep their permissions under their new subject
  ids. Each policy is written atomically with If-Match; running the migration again changes nothing.

  Example (add a twin subject for every user of an old IdP, keep the old one for now):
    dittoctl policies subjects migrate -f 'like(policyId,"org.example:customer-*")' \
        --match 'oldidp:(?P<sub>[0-9a-f-]{36})' --template 'newidp:fed-sub:\g<sub>' --dry-run

Options:
  --ids-file FILE                 Policy ids, one per line; - reads stdin.
  -f, --filter RQL                Migrate the policies of the things matching this.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces of the things for --filter.
  --match REGEX                   Subject ids to migrate (full match).  [required]
  --template TEMPLATE             The new subject id; \1 or \g<name> insert groups of --match.
                                  [required]
  --label TEXT                    Only in entries with this label. Repeatable.
  --remove-old                    Replace the matching subjects instead of adding next to them.
  --conflict-retries INTEGER RANGE
                                  How often to re-read and retry when a policy was changed
                                  concurrently.  [default: 3; x>=0]
  --allow-lockout                 Allow a change that removes your own WRITE permission on the
                                  policy (Ditto refuses it otherwise).
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl policies subjects remove`

```text
Usage: dittoctl policies subjects remove [OPTIONS] POLICY_ID LABEL SUBJECT_ID

  Remove a subject from an entry.

Options:
  --allow-lockout         Allow a change that removes your own WRITE permission on the policy (Ditto
                          refuses it otherwise).
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

### `dittoctl rql`

```text
Usage: dittoctl rql [OPTIONS] COMMAND [ARGS]...

  Check and format RQL filter expressions, without contacting Ditto.

Options:
  -h, --help  Show this message and exit.

Commands:
  fmt   Pretty-print an RQL filter, one condition per line.
  lint  Check an RQL filter; on error, show where it is.
```

#### `dittoctl rql fmt`

```text
Usage: dittoctl rql fmt [OPTIONS] EXPRESSION|@FILE|@-

  Pretty-print an RQL filter, one condition per line.

Options:
  --compact   Single line without whitespace (the form sent to Ditto).
  -h, --help  Show this message and exit.
```

#### `dittoctl rql lint`

```text
Usage: dittoctl rql lint [OPTIONS] EXPRESSION|@FILE|@-

  Check an RQL filter; on error, show where it is. Exit code 6 if invalid.

Options:
  -h, --help  Show this message and exit.
```

### `dittoctl things`

```text
Usage: dittoctl things [OPTIONS] COMMAND [ARGS]...

  Read, search, count, export and watch things.

Options:
  -h, --help  Show this message and exit.

Commands:
  array               Add items to, or remove them from, an array in each selected thing,...
  count               Count the things matching an RQL filter.
  create              Create a thing; fails if it already exists.
  delete              Delete the selected things.
  diff                Show the differences between a local JSON file and the thing in Ditto...
  edit                Edit a thing in $EDITOR; the changes are sent as a merge patch with...
  export              Export search results to a file, streaming: memory use stays flat...
  fields              Show which paths the matching things have, with JSON types, frequency and...
  get                 Retrieve one or more things.
  history             Show the changes of a thing per revision as NDJSON, oldest first (needs...
  import              Create (or replace) things from NDJSON or a JSON array, such as a 'things...
  migrate-definition  Move each selected thing to a new thing definition (Thing Model version),...
  patch               Merge-patch (RFC 7396) a part of each selected thing; PATH '/' patches...
  put                 Create or completely replace a thing.
  search              Search things with RQL, following the result cursor through all pages.
  set                 Set the value at PATH of each selected thing, creating missing parents.
  td                  Show the WoT Thing Description Ditto generates from the thing's...
  unset               Remove the value at PATH of each selected thing (absent values are fine,...
  verify              Check that PATH has the expected value in each selected thing, for...
  watch               Follow thing changes as they happen, one JSON object per line.
```

#### `dittoctl things array`

```text
Usage: dittoctl things array [OPTIONS] COMMAND [ARGS]...

  Add items to, or remove them from, an array in each selected thing, without losing concurrent
  changes.

Options:
  -h, --help  Show this message and exit.

Commands:
  add     Append the --items to the array at PATH of each selected thing.
  remove  Remove every occurrence of the --items from the array at PATH of each selected thing.
```

#### `dittoctl things array add`

```text
Usage: dittoctl things array add [OPTIONS] PATH [THING_ID]...

  Append the --items to the array at PATH of each selected thing.

  Each array is read with its ETag and written with If-Match, so concurrent changes are never lost;
  things whose array wouldn't change aren't written.

  Example:
    dittoctl things array add attributes/tags --items '["maintenance"]' --as-set -f 'eq(attributes/building,"B1")'

Options:
  --items JSON|@FILE              A JSON array of the items.  [required]
  --as-set                        Only add items that aren't present yet.
  --compare [deep|json]           Item equality: 'deep' (1 equals 1.0) or 'json' (canonical text).
                                  [default: deep]
  --conflict-retries INTEGER RANGE
                                  How often to re-read and retry when the array was changed
                                  concurrently.  [default: 3; x>=0]
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things array remove`

```text
Usage: dittoctl things array remove [OPTIONS] PATH [THING_ID]...

  Remove every occurrence of the --items from the array at PATH of each selected thing.

  Each array is read with its ETag and written with If-Match, so concurrent changes are never lost;
  things whose array wouldn't change aren't written.

  Example:
    dittoctl things array remove attributes/tags --items '["maintenance"]' -f 'eq(attributes/building,"B1")'

Options:
  --items JSON|@FILE              A JSON array of the items.  [required]
  --compare [deep|json]           Item equality: 'deep' (1 equals 1.0) or 'json' (canonical text).
                                  [default: deep]
  --conflict-retries INTEGER RANGE
                                  How often to re-read and retry when the array was changed
                                  concurrently.  [default: 3; x>=0]
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things count`

```text
Usage: dittoctl things count [OPTIONS]

  Count the things matching an RQL filter.

Options:
  -f, --filter RQL          RQL filter; @file reads it from a file.
  --no-validate             Send the filter as is, without checking it locally first.
  -n, --namespaces NS[,NS]  Namespaces to search in (default: the context's namespaces, else all).
                            Repeatable.
  -h, --help                Show this message and exit.
```

#### `dittoctl things create`

```text
Usage: dittoctl things create [OPTIONS] [THING_ID]

  Create a thing; fails if it already exists. Without THING_ID, Ditto generates the id.

  Examples:
    dittoctl things create org.example:sensor-1 -d '{"attributes":{"room":"lab"}}'
    dittoctl things create org.example:lamp-1 --definition https://example.org/models/lamp-1.0.0.tm.jsonld

Options:
  -d, --data JSON|@FILE|@-        The thing JSON (attributes, features, ...).
  --definition URL|NS:NAME:VERSION
                                  Thing definition; a WoT Thing Model URL makes Ditto generate the
                                  thing's skeleton.
  --policy-id TEXT                Use this existing policy instead of a new one.
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  -h, --help                      Show this message and exit.
```

#### `dittoctl things delete`

```text
Usage: dittoctl things delete [OPTIONS] [THING_ID]...

  Delete the selected things. Their policies are kept.

  Examples:
    dittoctl things delete org.example:sensor-1
    dittoctl things delete -f 'eq(attributes/decommissioned,true)' --dry-run

Options:
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things diff`

```text
Usage: dittoctl things diff [OPTIONS] THING_ID

  Show the differences between a local JSON file and the thing in Ditto (exit code 6 if they
  differ).

Options:
  --file FILE|-             Local JSON to compare with.  [required]
  --path TEXT               Compare only this part of the thing.
  -o, --output [text|json]  Output format: a unified diff, or a JSON list of {"op", "path", "old",
                            "new"} with op add, remove or replace and old being the value in Ditto
                            (default: text; agent mode: json).
  -h, --help                Show this message and exit.
```

#### `dittoctl things edit`

```text
Usage: dittoctl things edit [OPTIONS] THING_ID

  Edit a thing in $EDITOR; the changes are sent as a merge patch with If-Match.

  If the thing was changed by someone else in the meantime, nothing is written.

Options:
  --path TEXT             Only edit this part, e.g. attributes.
  --confirm-context NAME  Confirm a protected context without the prompt (for scripts).
  -h, --help              Show this message and exit.
```

#### `dittoctl things export`

```text
Usage: dittoctl things export [OPTIONS]

  Export search results to a file, streaming: memory use stays flat regardless of the number of
  things.

  Examples:
    dittoctl things export -f 'exists(features/temp)' --fields thingId,features/temp/properties --out temp.csv
    dittoctl things export -n org.example -o ndjson --out backup.ndjson

Options:
  -f, --filter RQL                RQL filter; @file reads it from a file.
  --no-validate                   Send the filter as is, without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces to search in (default: the context's namespaces, else
                                  all). Repeatable.
  --fields TEXT                   Field selector, e.g. thingId,attributes,features/temp/properties.
  --sort [+-]PATH[,...]           Sort order, e.g. +thingId.
  --limit INTEGER RANGE           Stop after this many things.  [x>=1]
  -o, --output [csv|ndjson|json|ids]
                                  Output format.  [default: csv]
  --no-progress                   Don't count the things first or show progress.
  --all                           Don't limit the output (agent mode shows the first 50 by default).
  --transport [auto|paging|sse]   How results are fetched: 'paging' through the search cursor, or
                                  Ditto's SSE search 'sse' stream. 'auto' streams when only thing
                                  ids are needed (-o ids) and the context allows it, else it pages.
                                  [default: auto]
  --columns PATH[,PATH]           Fixed columns (paths like attributes/location).
  --discover-rows INTEGER         Rows to inspect for column discovery; 0 inspects all (buffers the
                                  whole result).  [default: 100]
  --short-headers                 Use the shortest unambiguous path suffix as header.
  --delimiter TEXT                CSV delimiter.  [default: ,]
  --no-header                     Leave out the CSV header row.
  --excel                         CSV for Excel: UTF-8 BOM, timestamps as 'YYYY-MM-DD HH:MM:SS'
                                  (UTC).
  --out FILE                      Write to this file instead of stdout.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things fields`

```text
Usage: dittoctl things fields [OPTIONS]

  Show which paths the matching things have, with JSON types, frequency and example values.

  Ditto things are schemaless: this shows what to filter on (RQL) and which fields to select, also
  for things without a WoT model (for those, see 'things td'). Each line has path, types, count,
  share (of the inspected things) and examples.

  Examples:
    dittoctl things fields -n org.example
    dittoctl things fields -f 'eq(attributes/model,"X1")' --path features --sample 500

Options:
  -f, --filter RQL                RQL filter; @file reads it from a file.
  --no-validate                   Send the filter as is, without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces to search in (default: the context's namespaces, else
                                  all). Repeatable.
  --sample INTEGER RANGE          How many matching things to inspect: the first ones Ditto returns,
                                  not a random sample.  [default: 100; 1<=x<=10000]
  --path PATH                     Only paths below this one, e.g. attributes or features/temp.
  --examples INTEGER RANGE        Distinct example values per path.  [default: 3; 0<=x<=20]
  -o, --output [table|json|ndjson|csv]
                                  Output format (default: table on a terminal, ndjson otherwise).
  -h, --help                      Show this message and exit.
```

#### `dittoctl things get`

```text
Usage: dittoctl things get [OPTIONS] THING_ID...

  Retrieve one or more things.

  Examples:
    dittoctl things get org.example:sensor-1
    dittoctl things get org.example:sensor-1 --path attributes/location
    dittoctl things get org.example:sensor-1 --at-revision 42
    dittoctl things get org.example:sensor-1 org.example:sensor-2 --fields thingId,attributes -o table

Options:
  --path TEXT                     Only this part of the thing, e.g. attributes/location or
                                  features/temp/properties.
  --fields TEXT                   Field selector, e.g.
                                  thingId,attributes/location,features/temp/properties/value.
  --at-revision INTEGER           Read the thing as it was at this revision (needs Ditto history).
  --at-time TIMESTAMP             Read the thing as it was at this ISO-8601 time.
  --live                          Ask the device (live channel) instead of the twin; see --live-
                                  condition, --live-timeout-strategy.
  --live-timeout SECONDS          With --live: how long to wait for the device (Ditto's default:
                                  10s).  [1<=x<=60]
  -o, --output [json|table|ndjson|csv]
                                  Output format.  [default: json]
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things history`

```text
Usage: dittoctl things history [OPTIONS] THING_ID

  Show the changes of a thing per revision as NDJSON, oldest first (needs history retention in
  Ditto).

  Each line has the changed parts only, like 'things watch'; 'things get --at-revision N' shows the
  complete thing at a revision.

  Examples:
    dittoctl things history org.example:sensor-1 --from-revision -10
    dittoctl things history org.example:sensor-1 --from-time 2026-11-01T00:00:00Z --to-time 2026-11-02T00:00:00Z

Options:
  --from-revision INTEGER  First revision; negative counts back from the current one.
  --to-revision INTEGER    Last revision; 0 is the current one, negative counts back.
  --from-time TIMESTAMP    First point in time (ISO-8601).
  --to-time TIMESTAMP      Last point in time (ISO-8601).
  --fields TEXT            Fields of each change; add _context for the command that caused it.
                           [default: thingId,_revision,_modified,attributes,features]
  -f, --filter RQL         Only states matching this filter.
  --limit INTEGER RANGE    Stop after this many changes.  [x>=1]
  --all                    Don't limit the output (agent mode shows the first 50 by default).
  -h, --help               Show this message and exit.
```

#### `dittoctl things import`

```text
Usage: dittoctl things import [OPTIONS] FILE|-

  Create (or replace) things from NDJSON or a JSON array, such as a 'things export -o ndjson'.

  Each thing needs a thingId. Importing again is safe: existing things are reported as 'exists'
  (create) or left alone when unchanged (upsert).

  Examples:
    dittoctl things export -n org.example -o ndjson --out backup.ndjson
    dittoctl --context staging things import backup.ndjson --yes

Options:
  --mode [create|upsert]         'create' only creates things that don't exist; 'upsert' also
                                 replaces existing ones.  [default: create]
  --dry-run                      Show what would be sent, without writing anything.
  -y, --yes                      Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE   Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME         Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE    Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                       At most N requests per second.
  --journal FILE                 Record finished things here, to --resume later.
  --resume                       Skip the things already recorded in --journal.
  --failed-out FILE              Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]  Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                 error and its description; in a dry run, the first planned
                                 requests) or 'all', then a summary line. Default: none; agent mode:
                                 failures.
  -h, --help                     Show this message and exit.
```

#### `dittoctl things migrate-definition`

```text
Usage: dittoctl things migrate-definition [OPTIONS] [THING_ID]...

  Move each selected thing to a new thing definition (Thing Model version), optionally updating it.

  --dry-run lets Ditto compute the result without applying it (Ditto 3.7+).

  Example:
    dittoctl things migrate-definition --definition https://models.example.org/sensor-2.0.0.tm.jsonld \
        --init-defaults -f 'eq(definition,"https://models.example.org/sensor-1.0.0.tm.jsonld")' --dry-run

Options:
  --definition TM_URL            URL of the new WoT Thing Model.  [required]
  --payload JSON|@FILE           Attributes/features to merge, may use {{ thing-json:... }}.
  --patch-condition PATH=RQL     Only merge the payload at PATH if the RQL matches, e.g.
                                 features/temp=not(exists(features/temp)).
  --init-defaults                Initialize missing properties from the model's defaults.
  --ids-file FILE                Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL               Select by RQL filter; @file reads it.
  --no-validate                  Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]       Namespaces for --filter.
  --include-file FILE            Only things whose id is also in this file.
  --exclude-file FILE            Leave out things whose id is in this file.
  --dry-run                      Show what would be sent, without writing anything.
  -y, --yes                      Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE   Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME         Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE    Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                       At most N requests per second.
  --journal FILE                 Record finished things here, to --resume later.
  --resume                       Skip the things already recorded in --journal.
  --failed-out FILE              Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]  Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                 error and its description; in a dry run, the first planned
                                 requests) or 'all', then a summary line. Default: none; agent mode:
                                 failures.
  -h, --help                     Show this message and exit.
```

#### `dittoctl things patch`

```text
Usage: dittoctl things patch [OPTIONS] PATH [THING_ID]...

  Merge-patch (RFC 7396) a part of each selected thing; PATH '/' patches the whole thing.

  Unchanged values are skipped (--if-equal skip) unless --if-equal update is given. Things that
  don't exist are reported as not-found; they are never created.

  Examples:
    dittoctl things patch attributes/location -d '{"room":"lab"}' org.example:sensor-1
    dittoctl things patch / -d @patch.json -f 'eq(attributes/model,"X1")' --dry-run
    dittoctl things search -f 'exists(features/temp)' -o ids | dittoctl things patch features/temp/properties \
        -d '{"unit":"°C"}' --ids-file - --yes

Options:
  -d, --data JSON|@FILE|@-        The merge patch to apply.  [required]
  --replace-array                 Allow arrays in the patch (they replace the whole array).
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things put`

```text
Usage: dittoctl things put [OPTIONS] THING_ID

  Create or completely replace a thing.

  Example:
    dittoctl things put org.example:sensor-1 -d @sensor-1.json --if-match rev:7

Options:
  -d, --data JSON|@FILE|@-        The complete thing JSON.  [required]
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  -h, --help                      Show this message and exit.
```

#### `dittoctl things search`

```text
Usage: dittoctl things search [OPTIONS]

  Search things with RQL, following the result cursor through all pages.

  Examples:
    dittoctl things search -f 'eq(attributes/manufacturer,"ACME")' --fields thingId,attributes
    dittoctl things search -f 'gt(_modified,"2026-11-01T00:00:00Z")' --sort -_modified --limit 20
    dittoctl things search -n org.example -o ids > ids.txt

Options:
  -f, --filter RQL                RQL filter; @file reads it from a file.
  --no-validate                   Send the filter as is, without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces to search in (default: the context's namespaces, else
                                  all). Repeatable.
  --fields TEXT                   Field selector, e.g. thingId,attributes/location,_modified.
  --sort [+-]PATH[,...]           Sort order, e.g. -_modified or +attributes/name.
  --limit INTEGER RANGE           Stop after this many things.  [x>=1]
  --page-size INTEGER RANGE       Things per request.  [default: 200; 1<=x<=200]
  -o, --output [table|json|ndjson|csv|ids]
                                  Output format (default: table on a terminal, ndjson otherwise).
  --all                           Don't limit the output (agent mode shows the first 50 by default).
  --transport [auto|paging|sse]   How results are fetched: 'paging' through the search cursor, or
                                  Ditto's SSE search 'sse' stream. 'auto' streams when only thing
                                  ids are needed (-o ids) and the context allows it, else it pages.
                                  [default: auto]
  --columns PATH[,PATH]           Fixed columns (paths like attributes/location).
  --discover-rows INTEGER         Rows to inspect for column discovery; 0 inspects all (buffers the
                                  whole result).  [default: 100]
  --short-headers                 Use the shortest unambiguous path suffix as header.
  --delimiter TEXT                CSV delimiter.  [default: ,]
  --no-header                     Leave out the CSV header row.
  --excel                         CSV for Excel: UTF-8 BOM, timestamps as 'YYYY-MM-DD HH:MM:SS'
                                  (UTC).
  --out FILE                      Write to this file instead of stdout.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things set`

```text
Usage: dittoctl things set [OPTIONS] PATH VALUE [THING_ID]...

  Set the value at PATH of each selected thing, creating missing parents.

  VALUE is parsed as JSON if possible (42, true, {"a":1}), otherwise taken as a string. Things that
  don't exist are reported as not-found; they are never created.

  Examples:
    dittoctl things set attributes/location/room lab org.example:sensor-1
    dittoctl things set features/config/properties/interval 60 -f 'eq(attributes/model,"X1")'

Options:
  --string                        Treat VALUE as a string even if it is valid JSON.
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things td`

```text
Usage: dittoctl things td [OPTIONS] THING_ID

  Show the WoT Thing Description Ditto generates from the thing's definition (a Thing Model URL).

  --compact leaves out what follows from Ditto's conventions (forms, security, error schemas) and
  lists repeated parts once, which makes the description 2 to 12 times smaller, e.g. for an LLM.
  Paths are relative to the thing, or to features/<name> for a feature's properties, actions and
  events. A feature described exactly like an earlier one is shown as {"sameAs": "<feature>"}, a
  repeated data schema as {"$ref": "#/<JSON pointer to the first one>"}.

  Examples:
    dittoctl things td org.example:lamp-1
    dittoctl things td org.example:lamp-1 --feature Spot1
    dittoctl things td org.example:lamp-1 --with-features --compact

Options:
  --feature TEXT            The Thing Description of this feature instead.
  --with-features           Add the Thing Descriptions of all the thing's features, under
                            'features'.
  --compact                 Only titles, descriptions, data schemas and the path of each property,
                            action and event; single-line JSON when piped.
  --no-schema-descriptions  With --compact: leave out the descriptions inside data schemas (those of
                            properties, actions and events stay).
  -h, --help                Show this message and exit.
```

#### `dittoctl things unset`

```text
Usage: dittoctl things unset [OPTIONS] PATH [THING_ID]...

  Remove the value at PATH of each selected thing (absent values are fine, absent things are not-
  found).

  Example:
    dittoctl things unset attributes/obsolete -f 'exists(attributes/obsolete)'

Options:
  --ids-file FILE                 Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL                Select by RQL filter; @file reads it.
  --no-validate                   Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]        Namespaces for --filter.
  --include-file FILE             Only things whose id is also in this file.
  --exclude-file FILE             Leave out things whose id is in this file.
  --if-match ETAG|*               Only apply if the entity has this ETag (e.g. rev:5); '*' requires
                                  that it exists.
  --if-none-match ETAG|*          '*' only creates and never overwrites; with an ETag on reads,
                                  Ditto answers 304 if unchanged.
  --if-equal [update|skip|skip-minimizing-merge]
                                  What Ditto does if the new value equals the current one; 'skip'
                                  avoids no-op events.
  --condition RQL                 Only apply if the entity matches this RQL condition.
  --patch-condition PATH=RQL      Per-path condition for merge requests (Ditto 3.8+). Repeatable.
  --live-condition RQL            Route retrieves to the live channel if this matches.
  --live-timeout-strategy [fail|use-twin]
                                  What to do if the device doesn't answer a live request in time.
  --dry-run                       Show what would be sent, without writing anything.
  -y, --yes                       Don't ask; required above --max-affected things.
  --max-affected INTEGER RANGE    Above this many things, --yes is required.  [default: 100; x>=0]
  --confirm-context NAME          Confirm a protected context without the prompt (for scripts).
  --concurrency INTEGER RANGE     Requests in flight at the same time.  [default: 8; 1<=x<=64]
  --rate N                        At most N requests per second.
  --journal FILE                  Record finished things here, to --resume later.
  --resume                        Skip the things already recorded in --journal.
  --failed-out FILE               Write failed things here (usable as --ids-file to retry them).
  --results [none|failures|all]   Print a JSON line per thing on stdout: 'failures' (with Ditto's
                                  error and its description; in a dry run, the first planned
                                  requests) or 'all', then a summary line. Default: none; agent
                                  mode: failures.
  -h, --help                      Show this message and exit.
```

#### `dittoctl things verify`

```text
Usage: dittoctl things verify [OPTIONS] PATH [THING_ID]...

  Check that PATH has the expected value in each selected thing, for example after a bulk change.

  Prints the things that don't match as NDJSON and exits with code 6 if there are any.

  Example:
    dittoctl things verify features/config/properties/interval --equals 60 -f 'eq(attributes/model,"X1")'

Options:
  --equals JSON|@FILE       The expected value at PATH.  [required]
  --compare [deep|json]     Value equality: 'deep' (1 equals 1.0) or 'json' (canonical text).
                            [default: deep]
  --failed-out FILE         Write the things that don't match here (usable as --ids-file).
  --ids-file FILE           Thing ids, one per line (first column); - reads stdin.
  -f, --filter RQL          Select by RQL filter; @file reads it.
  --no-validate             Send the filter without checking it locally first.
  -n, --namespaces NS[,NS]  Namespaces for --filter.
  --include-file FILE       Only things whose id is also in this file.
  --exclude-file FILE       Leave out things whose id is in this file.
  -h, --help                Show this message and exit.
```

#### `dittoctl things watch`

```text
Usage: dittoctl things watch [OPTIONS]

  Follow thing changes as they happen, one JSON object per line. Stop with Ctrl+C, --duration or
  --max-events.

  Examples:
    dittoctl things watch -n org.example
    dittoctl things watch -f 'exists(features/temp)' --fields thingId,features/temp/properties/value
    dittoctl things watch --ids org.example:sensor-1 --max-events 1 --duration 2m

Options:
  -f, --filter RQL            RQL filter; @file reads it from a file.
  --no-validate               Send the filter as is, without checking it locally first.
  -n, --namespaces NS[,NS]    Namespaces to search in (default: the context's namespaces, else all).
                              Repeatable.
  --ids ID[,ID]               Only these things.
  --fields TEXT               Fields of each change to show (default: the changed parts).
  --extra-fields TEXT         Unchanged fields to add to each change, e.g. attributes/location.
  --duration DURATION         Stop watching after this long, e.g. 30s or 5m; 0 never stops (default;
                              agent mode: 30s).
  --max-events INTEGER RANGE  Stop after this many changes.  [x>=1]
  -h, --help                  Show this message and exit.
```

### `dittoctl whoami`

```text
Usage: dittoctl whoami [OPTIONS]

  Show the subjects Ditto derives from your credentials.

Options:
  -o, --output [json|text]  Output format.  [default: text]
  -h, --help                Show this message and exit.
```

### `dittoctl wot`

```text
Usage: dittoctl wot [OPTIONS] COMMAND [ARGS]...

  Web of Things (WoT): Ditto's Thing Directory. See also 'things td' and 'things migrate-
  definition'.

Options:
  -h, --help  Show this message and exit.

Commands:
  directory  Show Ditto's WoT Thing Directory description (/.well-known/wot, Ditto 3.9+).
```

#### `dittoctl wot directory`

```text
Usage: dittoctl wot directory [OPTIONS]

  Show Ditto's WoT Thing Directory description (/.well-known/wot, Ditto 3.9+).

Options:
  -h, --help  Show this message and exit.
```
