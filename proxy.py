"""Example Gatekeeper for Mampok.

A minimal mitmproxy reverse-proxy addon implementing the Gatekeeper
contract described in README.md: it sits in front of a tool container,
checks a JWT-based token/cookie pair against the secret Mampok writes
into the pod, and only forwards requests from authorized users.

This is a reference implementation to copy and adapt, not a component
Mampok itself depends on. Mampok only cares that whatever image you
point `auth_proxy_image` at speaks the contract in README.md.
"""

import json
import os

import jwt
from jwt import InvalidTokenError
from mitmproxy import http

# Mampok mounts the auth Secret at this path by default (config option
# `auth_config_mount_path`, see README.md). Adjust if you changed it.
AUTH_CONFIG_PATH = "/etc/config/auth-proxy.json"

# The four env vars Mampok always sets on the Gatekeeper container.
REDIRECT_HOST = os.getenv("REDIRECT_HOST", "")
REDIRECT_URL = os.getenv("REDIRECT_URL", "")
PROJECT_ID = os.getenv("PROJECT_ID", "")

COOKIE_NAME = "access_token_" + PROJECT_ID


def _forbidden(reason: str) -> http.Response:
    with open("403.html", "r", encoding="utf-8") as f:
        html = f.read().replace("{{reason}}", reason)
    return http.Response.make(403, html.encode("utf-8"), {"Content-Type": "text/html"})


def request(flow: http.HTTPFlow) -> None:
    # Read fresh on every request so a secret rotation (Mampok's
    # `update-auth`) takes effect immediately, without restarting the pod.
    with open(AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
        auth_config = json.load(f)
    secret_key = auth_config["secret_key"]
    groups = auth_config["groups"]
    owner = auth_config["owner"]
    users = auth_config["users"]

    query_token = flow.request.query.get("token")

    if query_token:
        # Step 1: a fresh link carries the token as a query parameter.
        # Only the signature is checked here; the token is handed off to
        # the browser as a cookie, and its claims are checked on the
        # next request (step 2 below).
        try:
            jwt.decode(query_token, secret_key, algorithms=["HS256"])
        except InvalidTokenError:
            flow.response = _forbidden("Invalid or missing token")
            return
        flow.response = http.Response.make(
            302,
            b"",
            {
                "Location": REDIRECT_HOST + REDIRECT_URL,
                "Set-Cookie": f"{COOKIE_NAME}={query_token}; Path={REDIRECT_URL}",
            },
        )
        return

    cookie_token = flow.request.cookies.get(COOKIE_NAME)
    if not cookie_token:
        flow.response = _forbidden("No token provided")
        return

    # Step 2: authorization happens here, against the token's claims.
    try:
        decoded = jwt.decode(cookie_token, secret_key, algorithms=["HS256"])
    except InvalidTokenError:
        flow.response = _forbidden("Invalid or missing token in cookies")
        return

    # `owner == "_public"` is this example's convention for "anyone with a
    # validly-signed token may access this project" -- it is not part of
    # the Mampok contract. Mampok just writes through whatever `owner`
    # value a Mamplan sets; your Gatekeeper is free to drop this rule,
    # add others, or ignore groups/users entirely.
    authorized = (
        decoded.get("username") == owner
        or decoded.get("username") in users
        or owner == "_public"
        or any(group in groups for group in decoded.get("groups", []))
    )
    if not authorized:
        flow.response = _forbidden("User does not belong to any authorized group")
    # else: leave flow.response unset, mitmproxy forwards the request as-is.
