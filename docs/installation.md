# Verified installation and instance lifecycle

AimiliVPN must be installed from the fixed repository and an immutable release
tag or full commit. A fresh systemd installation creates and starts only the JP
instance. Other countries remain absent until they appear with usable nodes in
the latest VPNGate response and an authenticated administrator creates them
through the Console lifecycle API.

## One-script installation and management

For the normal VPS flow, find a version such as `v1.0.0` on the project's
[Releases](https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases) or
[Tags](https://github.com/ericcartmanfatass/aimili-vpngate-fork/tags) page, then
replace `v1.0.0` below if needed and run this one line:

```bash
curl --fail --location "https://raw.githubusercontent.com/ericcartmanfatass/aimili-vpngate-fork/v1.0.0/install.sh" --output /tmp/aimilivpn-install.sh && sudo bash /tmp/aimilivpn-install.sh --ref v1.0.0
```

The installer obtains dependencies, checks out the fixed repository at the
selected tag/commit, compares its own SHA-256 with the checked-out installer,
configures systemd, starts the initial JP instance, and offers an interactive
first-login password reset when attached to a terminal. It never selects a
moving branch or silently installs a different version.

The same script can manage an existing installation:

```bash
sudo bash /opt/aimilivpn/install.sh --menu
sudo bash /opt/aimilivpn/install.sh --status
sudo bash /opt/aimilivpn/install.sh --web
sudo bash /opt/aimilivpn/install.sh --reset-password
sudo bash /opt/aimilivpn/install.sh --uninstall --yes
```

For an update, select install/update in the menu and enter the new immutable
tag or full commit. The installed entry downloads that exact version's
installer and hands control to it; the new installer then verifies itself
against the checked-out source before changing services.

The menu does not bypass lifecycle safety: fresh installation still creates JP
only, additional countries are created from the authenticated server catalog,
and uninstall preserves source/data. Permanent data or source deletion remains
an advanced `ml uninstall` operation with separate confirmation flags.

## Verify before running

Release assets must publish both `aimilivpn-VERSION.tar.gz` and `SHA256SUMS`.
Maintainers generate them from the signed/reviewed release tag with
`bash scripts/build-release.sh vX.Y.Z`; the deterministic archive and checksum file
are uploaded together.
Replace `vX.Y.Z` below with a published release tag:

```bash
VERSION=vX.Y.Z
curl --fail --location --remote-name \
  "https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases/download/${VERSION}/aimilivpn-${VERSION}.tar.gz"
curl --fail --location --remote-name \
  "https://github.com/ericcartmanfatass/aimili-vpngate-fork/releases/download/${VERSION}/SHA256SUMS"
grep " aimilivpn-${VERSION}.tar.gz$" SHA256SUMS | sha256sum --check --strict
tar -xzf "aimilivpn-${VERSION}.tar.gz"
cd "aimilivpn-${VERSION}"
sudo AIMILIVPN_REF="${VERSION}" bash install.sh
```

Never execute `curl | bash` or an installer fetched from `main`. The installer
accepts only a `vX.Y.Z` tag or full 40-character commit for remote deployment.
It records the repository, ref, resolved commit, and installer SHA-256 in
`/etc/aimilivpn/install-source.json` with mode 0600.
`AIMILIVPN_LOCAL_DEV=1` is a development-only escape hatch for testing a local
checkout; it intentionally skips release-ref verification and source metadata.

## Initial Console access

The installer never writes a plaintext password into the authentication JSON or
prints one into installation logs. After a fresh install, run the following as
root from an interactive terminal:

```bash
sudo ml password reset
```

The command generates a strong random Console password, atomically replaces the
stored hash, restarts `aimilivpn-console.service`, and prints the new password
exactly once to that terminal. Save it immediately, then use `ml web` to obtain
the loopback Console URL. `ml password` reports password status without
revealing any credential.

## Updates and rollback

Re-run a verified newer release with its tag in `AIMILIVPN_REF`. The default
update stops if the checkout is dirty or if the new commit is not a
fast-forward. `FORCE_UPDATE=1` is an explicit recovery action: before resetting,
the installer writes a Git bundle, working-tree patch, and status file under
`/var/backups/aimilivpn/TIMESTAMP/`.

Before an operational upgrade, also back up configuration and data:

```bash
sudo cp -a /etc/aimilivpn "/etc/aimilivpn.backup.$(date +%s)"
sudo cp -a /opt/aimilivpn/data "/opt/aimilivpn-data.backup.$(date +%s)"
```

Rollback by checking out the prior verified tag, restoring the backups, running
`systemctl daemon-reload`, and restarting the Console and retained instances.

## Instance lifecycle API

The Console listens on loopback and all lifecycle routes require a valid Console
session. Browsers never write `/etc`, allocate ports, or generate systemd units.

- `GET /api/instance-catalog` lists countries found in the latest VPNGate
  response, their usable node counts, allocated resource preview, and whether
  each is installed.
- `POST /api/instances/validate` with `{"country":"DE"}` validates a create.
- `POST /api/instances` creates and starts a catalog instance atomically.
- `GET /api/instances` and `GET /api/instances/{id}/status` query state.
- `POST /api/instances/{id}/service` with `start`, `stop`, or `restart` controls
  only that installer-managed unit.
- `DELETE /api/instances/{id}` requires `{"confirmation":"id"}` and retains
  data by default. Purging data additionally requires `retain_data:false` and
  `purge_data_confirmation:"purge:id"`.

Creation accepts only a current two-letter VPNGate catalog country and derives
the canonical instance ID from it. The backend allocates a free TUN device,
policy table, and UI/proxy ports, then validates host conflicts, environment
paths, and duplicates. It writes mode-0600 configuration, atomically
updates `instances.json`, runs `daemon-reload`, and uses `enable --now`. Any
failure restores the previous catalog and removes newly-created empty resources.
Deletion first stops and disables the service. The backend service owns policy
route cleanup during shutdown; configuration is then removed. Data is preserved
unless the separate purge confirmation is supplied.

## Generated systemd boundary

`aimilivpn@.service` runs the packaged manager with only `CAP_NET_ADMIN` and
`CAP_NET_RAW` in its bounding/ambient sets. `aimilivpn-console.service` has an
empty capability bounding set. Both use `NoNewPrivileges`, `PrivateTmp`,
`ProtectHome`, `ProtectSystem=strict`, `UMask=0077`, restricted address
families/namespaces, kernel/control-group protection, and native system-call
architecture. The backend may write only `/opt/aimilivpn/data`; the Console may
write that data directory and `/etc/aimilivpn` for lifecycle transactions.

Backend environment files are `/etc/aimilivpn/{country}.env` and are mode 0600.
JP/US/KR retain their compatible preferred slots. Other countries use the first
free managed slot starting at tun13/table 113/proxy 7931/UI 18791. Allocations
are persisted in `instances.json` and never renumbered when the upstream country
list changes. The Console environment and instance API token are also mode 0600.

## Network and uninstall behavior

The installer does not modify DNS or `/etc/resolv.conf`. Before applying
`rp_filter=2`, it records the original live values in
`/etc/aimilivpn/network-changes.json`. If an existing
`/etc/sysctl.d/99-aimilivpn.conf` was present, it is backed up before replacement.

`ml uninstall --yes` stops/disables services, removes instance-owned policy
tables and configuration, restores the pre-install sysctl file when available
(otherwise removes the AimiliVPN file), reapplies sysctl settings, and finally
restores the recorded pre-install live `rp_filter` values. Instance
data and source are retained by default. Data/source deletion each requires its
own explicit confirmation flags.
