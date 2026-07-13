# TLS reverse proxy for remote management

AimiliVPN does not implement native TLS. The Console and single-instance Web UI
listen on `127.0.0.1` by default and must remain unreachable from the public
network. Remote management is supported only through a TLS-terminating reverse
proxy on the same host.

The random secret path reduces unsolicited scanning noise. It is not
authentication, authorization, or transport encryption. A password and HTTPS are
still required.

## Enable the local proxy trust boundary

Add these values to the service environment file that owns the management UI:

```ini
AIMILIVPN_TRUST_PROXY_HEADERS=1
AIMILIVPN_TRUSTED_PROXY_ADDRESSES=127.0.0.1,::1
```

For the unified Console this is `/etc/aimilivpn/console.env`. For a legacy
single-instance service, add the values to that instance's environment file.
Then restart the affected service:

```bash
sudo systemctl daemon-reload
sudo systemctl restart aimilivpn-console.service
```

Proxy headers are ignored unless `AIMILIVPN_TRUST_PROXY_HEADERS=1`. Even when it
is enabled, only explicitly listed loopback IP addresses are accepted; non-loopback
entries are discarded. AimiliVPN only consumes `X-Forwarded-Proto` for deciding
whether a session Cookie may carry `Secure`. It does not trust forwarded client
addresses for authentication.

## Nginx example

Replace the hostname and certificate paths. Keep the upstream on loopback:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name vpn.example.com;

    ssl_certificate     /etc/letsencrypt/live/vpn.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vpn.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8788;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Do not expose port `8788` in a firewall or cloud security group. Only ports 80
(when needed for certificate issuance/redirects) and 443 should be public.

## Caddy example

Caddy sets `X-Forwarded-Proto` for reverse-proxied requests and can manage the
public certificate automatically when DNS points at the host:

```caddyfile
vpn.example.com {
    reverse_proxy 127.0.0.1:8788
}
```

Do not place an untrusted CDN or another proxy in front without separately
configuring that proxy's trust boundary.

## Local emergency access

If TLS is not ready, use an SSH tunnel instead of opening the management port:

```bash
ssh -L 8788:127.0.0.1:8788 root@your-server
```

Run `ml web` on the server to retrieve the authenticated secret-path URL, then
replace its host with `127.0.0.1` and open it through the tunnel. Cookies used over
the direct HTTP tunnel intentionally omit `Secure`; cookies received through a
trusted HTTPS reverse proxy include `Secure; HttpOnly; SameSite=Lax`.
