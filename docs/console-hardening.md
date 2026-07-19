# Console input and resource controls

The unified Console applies the following protections by default:

- JSON request bodies are limited to 64 KiB. Invalid `Content-Length` values
  receive HTTP 400 and oversized bodies receive HTTP 413.
- Each accepted connection has a 10-second socket timeout.
- At most 32 request-handler threads run concurrently. Additional accepted
  connections receive HTTP 503 instead of creating unbounded threads.
- Login attempts are limited per client IP to 5 attempts in a 60-second window.
  Successful authentication resets that client's counter.
- Login and backend failures return generic messages. Exception details remain
  only in server-side audit output.
- Service actions accept only `aimilivpn@<instance>.service` names that match the
  selected installer-managed instance. Instance environment files must be the
  matching `<instance>.env` file under the configured AimiliVPN configuration
  directory.
- Expired sessions are removed during authorization checks. Logout removes the
  server-side token, and changes to username, password hash, secret path, host,
  or port revoke all Console sessions.

The resource limits can be adjusted in `/etc/aimilivpn/console.env`:

```ini
CONSOLE_MAX_REQUEST_BODY_BYTES=1048576
CONSOLE_REQUEST_TIMEOUT_SECONDS=10
CONSOLE_MAX_REQUEST_THREADS=32
CONSOLE_LOGIN_RATE_LIMIT_ATTEMPTS=5
CONSOLE_LOGIN_RATE_LIMIT_WINDOW_SECONDS=60
```

The parser rejects out-of-range settings and falls back to the secure defaults.
Do not raise these values merely to compensate for a public, unprotected Console;
the Console must remain on loopback behind the TLS proxy described in
[`reverse-proxy.md`](reverse-proxy.md).
