# Verified installation and instance lifecycle

AimiliVPN must be installed from the fixed repository and an immutable release
tag or full commit. A fresh systemd installation creates and starts only the JP
instance. KR and US remain absent until an authenticated administrator creates
them through the Console lifecycle API.

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

- `GET /api/instance-catalog` lists the verified JP/KR/US templates and whether
  each is installed.
- `POST /api/instances/validate` with `{"country":"US"}` validates a create.
- `POST /api/instances` creates and starts a catalog instance atomically.
- `GET /api/instances` and `GET /api/instances/{id}/status` query state.
- `POST /api/instances/{id}/service` with `start`, `stop`, or `restart` controls
  only that installer-managed unit.
- `DELETE /api/instances/{id}` requires `{"confirmation":"id"}` and retains
  data by default. Purging data additionally requires `retain_data:false` and
  `purge_data_confirmation:"purge:id"`.

Creation validates the canonical ID, TUN device, policy table, UI/proxy ports,
environment path, and duplicates. It writes mode-0600 configuration, atomically
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

Backend environment files are `/etc/aimilivpn/{jp,kr,us}.env` and are mode
0600. Their resource values must match the catalog: JP uses tun10/table 110/
7928/18788, US tun11/table 111/7929/18789, and KR tun12/table 112/7930/18790.
The Console environment and instance API token are also mode 0600.

## Network and uninstall behavior

The installer does not modify DNS or `/etc/resolv.conf`. It records its
`rp_filter=2` settings in `/etc/aimilivpn/network-changes.json`. If an existing
`/etc/sysctl.d/99-aimilivpn.conf` was present, it is backed up before replacement.

`ml uninstall --yes` stops/disables services, removes instance-owned policy
tables and configuration, restores the pre-install sysctl file when available
(otherwise removes the AimiliVPN file), and reapplies sysctl settings. Instance
data and source are retained by default. Data/source deletion each requires its
own explicit confirmation flags.
