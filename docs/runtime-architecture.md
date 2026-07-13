# Backend runtime architecture

The packaged backend builds one `ManagerRuntimeContext` and exposes its stable
dependencies through `ManagerRuntimeServices`. New backend code should depend on
the injected configuration, repository, connection, monitoring, lifecycle, log,
or Web API runtime instead of importing the compatibility `vpngate_manager`
module or reading its exported globals.

`ManagerRuntimeConfig` owns process-level configuration. It embeds the single
`AppConfig` created by `core.config.load_config()`, so shared settings such as the
VPNGate API URL, data directory, listen addresses, proxy trust, OpenVPN command,
TUN device, policy table, country allowlist, and fetch policy are parsed once.

## Connection state

The persisted state and Web API expose `connection_state` with these stable
values:

| State | Meaning |
| --- | --- |
| `idle` | No connection or maintenance operation is active. |
| `fetching` | Candidate nodes are being fetched. |
| `probing` | Candidate nodes are being tested. |
| `connecting` | OpenVPN is establishing a selected connection. |
| `connected` | OpenVPN and the selected node are active. |
| `switching` | A replacement node is being selected. |
| `failed` | The latest connection or maintenance transition failed. |

The legacy `is_connecting` field remains for compatibility and is derived
consistently by the shared state transition helper. New code should use
`ConnectionPhase` and `set_connection_phase()`.

## Background lifecycle

`ManagerThreadRuntime` is the owner of background tasks. It tracks every thread,
provides an interruptible stop event to monitoring and the proxy listener,
collects uncaught task exceptions, and joins tracked threads during shutdown.
When the Web server returns or raises, the service runtime always requests task
shutdown and stops the active OpenVPN process.

## API errors

Unexpected Web API exceptions are logged server-side using the operation and
exception type. Clients receive a stable `error_code` and a generic message;
exception text is not returned. Expected validation failures may retain their
specific safe client message. Detailed API contracts are finalized in P5.
