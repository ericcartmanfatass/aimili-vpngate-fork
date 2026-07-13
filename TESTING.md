# Testing and support baseline

## Supported runtime

- Production target: Linux.
- Supported distributions in CI: Ubuntu 22.04 and Ubuntu 24.04.
- Supported Python versions in CI: CPython 3.10 and 3.12.
- Frontend security test runtime in CI: Node.js 22.
- Reference development version: CPython 3.12, recorded in `.python-version`.
- The application uses the Python standard library; frontend DOM security tests
  use only Node.js built-ins and install no npm dependencies.

Other Linux distributions handled by `install.sh` remain install targets, but the
two Ubuntu LTS releases above are the repeatable CI contract. Windows is useful
for source-level development only and is not a supported deployment target.

## Local verification

Run the same checks as CI from the repository root:

```bash
python -m compileall -q aimilivpn console_server.py proxy_server.py vpngate_manager.py vpn_utils.py tests
bash -n install.sh scripts/build-release.sh
python -m unittest discover -s tests -p 'test*.py'
node --test tests/frontend_dom.test.js
```

Tests replace network, OpenVPN, process, and systemd interactions with fakes or
mocks. A unit-test run must not require a live VPN, public network access,
systemd, or root privileges.

## Managed Windows sandbox note

The managed Windows development sandbox may deny writes inside directories
created by `tempfile.TemporaryDirectory()`, even when the parent directory is
writable. On 2026-07-13 this produced exactly 113 `PermissionError` errors in a
460-test run; the same revision passed all 460 tests outside that sandbox.

Treat this signature as an environment limitation, not as a business regression:

- errors are `PermissionError` or `WinError 5` under a temporary directory;
- there are no failed assertions; and
- the complete suite passes in Linux CI or in an unrestricted local environment.

Do not weaken file-permission tests to accommodate this sandbox. Linux CI is the
authoritative release signal.

## Security regression map

- Authentication primitives and migration: `tests/test_auth.py`,
  `tests/test_console_modules.py`, and `tests/test_web_routes.py`.
- Web and Console request-body limits: `tests/test_http_utils.py` and
  `tests/test_console_routes.py`.
- Web authorization and session cookies: `tests/test_web_server.py` and
  `tests/test_web_routes.py`.
- TLS proxy trust, loopback enforcement, and Console cookies:
  `tests/test_proxy_trust.py`, `tests/test_console_routes.py`, and
  `tests/test_console_server_wrapper.py`.
- Console request timeout, bounded concurrency, login throttling, managed service
  boundaries, and session revocation: `tests/test_console_routes.py`,
  `tests/test_console_security.py`, `tests/test_console_server_wrapper.py`, and
  `tests/test_console_modules.py`.
- Runtime configuration, connection-state transitions, background shutdown, and
  safe API error mapping: `tests/test_manager_config.py`,
  `tests/test_connection_state.py`, `tests/test_manager_threads.py`,
  `tests/test_service_runtime.py`, and `tests/test_api_errors.py`.
- Versioned JSON/SQLite repository contracts, migration backup/rollback,
  region quality/risk routing, and persistent provider caching:
  `tests/test_storage_contract.py`, `tests/test_repository_facade.py`,
  `tests/test_regions.py`, and `tests/test_scamalytics.py`.
- Versioned API aliases, bounded list queries, stable error identifiers,
  idempotent background operations, and mutation auditing:
  `tests/test_api_contract.py`, `tests/test_operations.py`,
  `tests/test_http_utils.py`, `tests/test_web_routes.py`, and
  `tests/test_web_server.py`.
- Console/Web listen defaults: `tests/test_console_modules.py`,
  `tests/test_ui_config.py`, and the stage-specific tests added with network
  hardening.
- Installer and systemd static checks: `tests/test_install_script.py` plus
  `bash -n install.sh scripts/build-release.sh` in CI.
- Verified source pinning, JP-only defaults, instance catalog create/delete
  rollback, resource conflicts, data retention, and sysctl restoration:
  `tests/test_install_script.py`, `tests/test_instance_lifecycle.py`,
  `tests/test_console_routes.py`, and `tests/test_cli_parser.py`.
- Frontend inline-event removal, safe DOM rendering for hostile node/status/log/
  instance metadata, versioned API pagination, and controlled Console lifecycle
  calls: `tests/test_frontend_security.py`, `tests/frontend_dom.test.js`,
  `tests/test_static_assets.py`, and `tests/test_web_templates.py`.

Network/session security changes must update these tests before their call sites.
