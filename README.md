# Mampok Gatekeeper Example

An example **Gatekeeper**: a sidecar reverse proxy that Mampok can deploy in
front of a tool container to restrict access to authorized users. This repo
shows one way to implement the contract Mampok expects from any
`auth_proxy_image`; it is a reference to copy and adapt, not a dependency of
Mampok itself.

Verified compatible with [Mampok](https://github.com/loosolab/MAMPOK) v3.2.0.

## What it does

This particular Gatekeeper is a small [mitmproxy](https://mitmproxy.org/)
addon (`proxy.py`) that reverse-proxies to the main tool container and only
forwards requests carrying a validly-signed, authorized JWT. Everything
below is specific to this implementation; the only part Mampok actually
requires is described in [The Mampok contract](#the-mampok-contract).

### Request flow

1. **Link with `?token=<jwt>`.** The token's signature is checked (not yet
   its claims). On success, the client is redirected and the token is set
   as a cookie (`access_token_<PROJECT_ID>`). On failure: `403`.
2. **Follow-up requests carry that cookie.** This is where authorization
   actually happens: the cookie's JWT is decoded and the request is let
   through if the token's `username` matches the project's `owner`, is
   listed in `users`, or if any of the token's `groups` is in the
   project's `groups`. Otherwise: `403`.
3. **No token at all** (neither query param nor cookie): `403`.

There is no expiry check, and none is expected — see
[Tokens and revocation](#tokens-and-revocation).

### The `_public` example policy

If a project's `owner` is set to the literal string `"_public"`, this
Gatekeeper grants access to anyone holding a validly-signed token,
regardless of their claimed username or groups.

**This is a convention of this example, not part of the Mampok contract.**
Mampok only ever writes through whatever `owner` value a Mamplan's
`service.owner` field holds; it has no special handling for `"_public"` or
any other value. A Gatekeeper you write is free to keep this rule, drop it,
or implement a completely different authorization policy (e.g. users-only,
ignoring groups entirely).

### Tokens and revocation

Tokens issued by Mampok carry no `exp` claim, only `{groups, username,
iat}`. Revocation works via secret rotation instead: Mampok's `update-auth`
command generates a new `secret_key`, which invalidates every
previously-issued token for that project at once.

## The Mampok contract

This is what Mampok guarantees to **any** Gatekeeper image, regardless of
its internal logic. A compliant Gatekeeper must be self-sufficient: Mampok
does not override the image's `command`/`args`, so it must know how to read
the mounted secret and act as a reverse proxy using only the following.

**Environment variables** set on the Gatekeeper container:

| Variable       | Meaning                                              |
| -------------- | ----------------------------------------------------- |
| `REVERSE_PORT` | Port of the main container to reverse-proxy to        |
| `REDIRECT_HOST`| Host to redirect to after a successful token exchange  |
| `REDIRECT_URL` | Path to redirect to after a successful token exchange  |
| `PROJECT_ID`   | The project's ID, e.g. for naming a per-project cookie |

**Secret volume:** a Kubernetes Secret is mounted at
`auth_config_mount_path` (default `/etc/config`), containing a single key
`auth-proxy.json` shaped:

```json
{
  "secret_key": "...",
  "owner": "someuser",
  "users": ["alice", "bob"],
  "groups": ["some-group"]
}
```

`secret_key` is the HMAC secret used to sign/verify tokens; `owner`,
`users` and `groups` are exactly the values from the Mamplan's
`service.owner`/`service.users`/`service.groups` fields, passed through
unmodified. What a Gatekeeper does with them (or whether it reads
`auth-proxy.json` fresh per request, as this example does, to pick up
secret rotations without a restart) is entirely up to the implementation.

**Config (Mampok's `config.json`, under `auth_proxy`):**

| Field                | Required | Default | Meaning                                   |
| --------------------- | -------- | ------- | ------------------------------------------ |
| `auth_proxy_image`    | yes      | —       | The Gatekeeper image to deploy             |
| `proxy_port`          | no       | `8080`  | Port the Gatekeeper listens on             |
| `auth_annotations`    | no       | `{}`    | Extra Ingress annotations                  |
| `image_pull_secrets`  | no       | `[]`    | Pull secrets for the proxy image           |
| `project_auth_path`   | no       | `""`    | Local `project_auth.json` path (optional)  |

Resource limits/requests default to `100m`/`128Mi` CPU/memory and can be
overridden per Mamplate via `proxy_resources`.

**Not part of the contract:** the HTTP flow (redirect-then-cookie, which
status codes to use for which failure, whether/how to check token
expiry) is entirely up to the Gatekeeper image. This repo shows one
working choice.

## Running it

```sh
docker build -t mampok-gatekeeper-example .
docker run -p 8080:8080 \
  -e REVERSE_PORT=5000 \
  -e REDIRECT_HOST=https://example.org \
  -e REDIRECT_URL=/my-project \
  -e PROJECT_ID=my-project \
  -v /path/to/auth-proxy.json:/etc/config/auth-proxy.json:ro \
  mampok-gatekeeper-example
```

To point a Mamplan/config at it, set `auth_proxy.auth_proxy_image` to the
built image (see [The Mampok contract](#the-mampok-contract) above).

## License

MIT, see [LICENSE](LICENSE).
