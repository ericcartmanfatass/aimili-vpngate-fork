# Release acceptance

A release is blocked until every item below has evidence for the exact candidate
commit. Passing unit tests on Windows is useful during development but is not a
substitute for Linux CI or the disposable-host lifecycle drill.

## 1. Candidate identity and Linux source gate

Record the candidate tag, full commit, artifact SHA-256, CI run URL, operating
systems, and Python versions. The required CI matrix is Ubuntu 22.04/24.04 with
CPython 3.10/3.12 and Node.js 22.

Run from a clean Linux checkout:

```bash
bash scripts/release-acceptance.sh | tee release-source-acceptance.log
git status --short
```

The command compiles all entry points, checks shell syntax, runs the full Python
and hostile-DOM suites, performs the legacy authentication/JSON migration and
rollback drill, and checks the Git diff. The final status must be zero and the
working tree must be clean. Attach the log to the release evidence; do not add
it to the source archive.

## 2. Manual security review

Review the exact candidate, not an older CI run. Record the reviewer and result
for each boundary:

- Web and Console default listeners are loopback. IPv6 Web fallback is also
  loopback, and public management uses only the documented TLS reverse proxy.
- HTTPS login through a trusted loopback proxy sets `Secure; HttpOnly;
  SameSite=Lax`; direct HTTP does not claim transport security.
- Web and Console store PBKDF2 hashes, revoke affected sessions after credential
  changes, bound request bodies/threads/timeouts, and throttle login attempts.
- Access, application, and JSON logs redact secret paths, credentials, private
  key blocks, tokens, and provider secrets. Public APIs omit raw OpenVPN config
  and provider responses.
- Console lifecycle calls accept only server catalog countries and backend-owned
  resource allocation. Browser input never supplies systemd, path, TUN, table,
  or port values.

The regression-to-code map is maintained in [`../TESTING.md`](../TESTING.md).
Any discrepancy blocks the release even if tests pass.

## 3. Migration and rollback drill

The source gate runs this independently, and CI runs it on every matrix member:

```bash
python3 scripts/release_migration_drill.py
```

Expected JSON contains `"status": "passed"`, confirms plaintext authentication
removal, reports two migrated documents, and lists verified rollback checksums.
The drill uses temporary data only. For a production upgrade, separately back
up `/etc/aimilivpn` and `/opt/aimilivpn/data` as documented in
[`installation.md`](installation.md).

## 4. Disposable Ubuntu host lifecycle

Use a brand-new Ubuntu 22.04 or 24.04 VPS/VM with TUN enabled and take a provider
snapshot first. Do not run this acceptance on a host containing user data.
Install the previous verified release, seed representative legacy JSON and
authentication configuration, then upgrade using the candidate's verified
archive and immutable `AIMILIVPN_REF`.

On the candidate, collect evidence for all of the following:

1. Installation succeeds and initially creates only the JP instance.
2. `systemctl is-active aimilivpn-console aimilivpn@jp` succeeds; `ss -lntp`
   shows Console, Web, and proxy upstreams only on loopback.
3. The VPNGate refresh populates the dynamic country catalog. Create one
   non-JP country from Console and verify its persisted TUN, policy table, and
   ports do not conflict with JP.
4. Connect a node, confirm proxy egress through the managed local proxy,
   disconnect, reconnect, restart both instance and Console services, and
   confirm state remains operable.
5. Verify migrated authentication contains no plaintext `password`; exercise
   JSON-to-SQLite migration, inspect its backup summary, then restore the JSON
   backup and run with `STORAGE_BACKEND=json`.
6. Roll back to the previous verified release and restore configuration/data
   backups. Confirm the retained JP instance starts.
7. Reinstall the candidate, run `ml uninstall --yes`, and confirm services,
   instance routes, and AimiliVPN-owned sysctl state are removed while data and
   source remain. On this disposable host only, separately test the explicit
   data/source deletion confirmations.

Capture sanitized command output, service status, listener tables, relevant
journal excerpts, and the release artifact checksum. Never attach passwords,
session cookies, secret paths, API keys, proxy credentials, or OpenVPN configs.

## 5. Required sign-off

Record these fields in the release ticket or release notes:

| Gate | Required evidence |
| --- | --- |
| Candidate identity | tag, full commit, artifact SHA-256 |
| Linux CI | successful run URL for the complete matrix |
| Security review | reviewer, date, five boundary results |
| Migration/rollback | drill output plus backup-summary checksum evidence |
| Fresh host lifecycle | OS/image, TUN, install through uninstall evidence |
| Documentation | README, MIGRATION, SECURITY review result |

Missing, partial, or locally simulated evidence is a release blocker.
