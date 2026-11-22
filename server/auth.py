"""Access-token validation for the Abarpay resource server (OIDC).

Abarpay's API is a *resource server*: it validates RS256 access tokens issued by
Auth0 (business owners and employees) and Microsoft Entra ID (internal SaaS
staff). The ID token is client material and is never accepted as an API
credential - an ID token carries the client's audience, so it fails the
audience check below.

- JWKS is fetched over HTTPS with per-kid caching and rotation.
- alg=none and every algorithm other than RS256 are rejected.
- iss, aud, exp and nbf (when present) are validated with bounded clock skew.
- The subject maps to users.external_sub: sub for Auth0; oid+tid for Entra
  (with idp='entra').

This module has no database access and no FastAPI dependency, so it can be
tested with an in-memory test JWKS without any network.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TokenValidationError(Exception):
    """An access token was rejected. 'code' is stable for API responses."""

    code = "invalid_token"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class InvalidTokenError(TokenValidationError):
    code = "invalid_token"


class TokenExpiredError(TokenValidationError):
    code = "token_expired"


class TokenNotYetValidError(TokenValidationError):
    code = "token_not_yet_valid"


class InvalidAudienceError(TokenValidationError):
    code = "invalid_audience"


class InvalidIssuerError(TokenValidationError):
    code = "invalid_issuer"


class UnsupportedAlgorithmError(TokenValidationError):
    code = "unsupported_algorithm"


class JwksError(TokenValidationError):
    code = "jwks_error"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ENTRA_AUTHORITY_SUFFIX = "/v2.0"


@dataclass(frozen=True)
class Issuer:
    """One trusted OIDC issuer and the audience our API expects from it."""

    issuer: str
    audience: str
    kind: str  # 'auth0' | 'entra'
    discovery_uri: str | None = None
    # Auth0 API access tokens carry email/name in namespaced claims set by an
    # Action (e.g. https://abarpay.app/email), not at the root. Set by
    # AuthConfig.from_env; leave empty to read only root claims.
    email_claim: str | None = None
    name_claim: str | None = None


@dataclass(frozen=True)
class AuthConfig:
    """Trusted issuers plus the resource-server knobs.

    Read from environment variables by from_env() so that config.py stays
    untouched. With no issuer configured every token is rejected, which is the
    safe default for a resource server.
    """

    issuers: tuple[Issuer, ...] = ()
    clock_skew_seconds: float = 60.0
    jwks_ttl_seconds: float = 300.0
    http_timeout_seconds: float = 10.0
    secure_cookies: bool = True
    cookie_samesite: str = "lax"

    @property
    def enabled(self) -> bool:
        return bool(self.issuers)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AuthConfig":
        env = os.environ if environ is None else environ

        def get(name: str) -> str:
            return (env.get(name) or "").strip()

        def get_float(name: str, default: float) -> float:
            try:
                value = get(name)
                return float(value) if value else default
            except ValueError:
                return default

        def get_bool(name: str, default: bool) -> bool:
            value = get(name).lower()
            if not value:
                return default
            return value in {"1", "true", "yes", "si", "sí", "on"}

        issuers: list[Issuer] = []

        auth0_domain = get("AUTH0_DOMAIN").rstrip("/")
        auth0_audience = get("AUTH0_AUDIENCE")
        auth0_email_claim = get("AUTH0_EMAIL_CLAIM") or "https://abarpay.app/email"
        auth0_name_claim = get("AUTH0_NAME_CLAIM") or "https://abarpay.app/name"
        if auth0_domain and auth0_audience:
            if "://" not in auth0_domain:
                auth0_domain = "https://" + auth0_domain
            issuer = auth0_domain.rstrip("/") + "/"
            discovery = issuer + ".well-known/openid-configuration"
            issuers.append(
                Issuer(
                    issuer=issuer,
                    audience=auth0_audience,
                    kind="auth0",
                    discovery_uri=discovery,
                    email_claim=auth0_email_claim,
                    name_claim=auth0_name_claim,
                )
            )

        entra_tenant = get("ENTRA_TENANT").rstrip("/")
        entra_audience = get("ENTRA_AUDIENCE")
        if entra_tenant and entra_audience:
            authority = (
                entra_tenant
                if entra_tenant.startswith("https://")
                else f"https://login.microsoftonline.com/{entra_tenant}"
            ).rstrip("/")
            if not authority.endswith(_ENTRA_AUTHORITY_SUFFIX):
                authority += _ENTRA_AUTHORITY_SUFFIX
            discovery = f"{authority}/.well-known/openid-configuration"
            issuers.append(
                Issuer(
                    issuer=authority,
                    audience=entra_audience,
                    kind="entra",
                    discovery_uri=discovery,
                )
            )

        secure = get_bool("SECURE_COOKIES", True)
        samesite = get("COOKIE_SAMESITE").lower() or "lax"
        if samesite not in {"lax", "strict", "none"}:
            samesite = "lax"

        return cls(
            issuers=tuple(issuers),
            clock_skew_seconds=get_float("OIDC_CLOCK_SKEW_SECONDS", 60.0),
            jwks_ttl_seconds=get_float("OIDC_JWKS_TTL_SECONDS", 300.0),
            http_timeout_seconds=get_float("OIDC_HTTP_TIMEOUT_SECONDS", 10.0),
            secure_cookies=secure,
            cookie_samesite=samesite,
        )


# ---------------------------------------------------------------------------
# JWKS providers
# ---------------------------------------------------------------------------


class JwksProvider(ABC):
    """Fetches the full JWKS and returns a {kid: jwk} mapping."""

    @abstractmethod
    def fetch(self) -> dict[str, dict[str, Any]]:
        ...


class StaticJwksProvider(JwksProvider):
    """SIMULADO/test provider: a fixed {kid: jwk} mapping, no network."""

    def __init__(self, keys_by_kid: Mapping[str, Mapping[str, Any]]) -> None:
        self._keys = {str(kid): dict(jwk) for kid, jwk in keys_by_kid.items()}

    def fetch(self) -> dict[str, dict[str, Any]]:
        return dict(self._keys)


class DiscoveryJwksProvider(JwksProvider):
    """Resolves jwks_uri from OIDC discovery, then fetches the keys."""

    def __init__(
        self,
        discovery_uri: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._discovery_uri = discovery_uri
        self._timeout = timeout
        self._transport = transport
        self._jwks_uri: str | None = None

    def _client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(self._timeout),
            "headers": {"Accept": "application/json"},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def fetch(self) -> dict[str, dict[str, Any]]:
        try:
            with self._client() as client:
                if self._jwks_uri is None:
                    doc = client.get(self._discovery_uri)
                    doc.raise_for_status()
                    self._jwks_uri = str(doc.json()["jwks_uri"])
                response = client.get(self._jwks_uri)
                response.raise_for_status()
                keys = response.json().get("keys", [])
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise JwksError(f"failed to fetch JWKS: {exc}") from exc

        result: dict[str, dict[str, Any]] = {}
        for key in keys:
            if isinstance(key, dict) and key.get("kid") and key.get("kty") == "RSA":
                result[str(key["kid"])] = key
        return result


# ---------------------------------------------------------------------------
# JWKS cache with rotation by kid
# ---------------------------------------------------------------------------


class JwksCache:
    """Caches JWKS keys by kid and refreshes on unknown kid or TTL expiry."""

    def __init__(
        self,
        provider: JwksProvider,
        *,
        ttl_seconds: float = 300.0,
        now: Any = None,
    ) -> None:
        self._provider = provider
        self._ttl = ttl_seconds
        self._now = now or time.time
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float | None = None
        self._lock = threading.Lock()

    def get_key(self, kid: str | None) -> dict[str, Any]:
        if not kid:
            raise InvalidTokenError("token is missing the 'kid' header")
        with self._lock:
            now = self._now()
            stale = (
                self._fetched_at is None
                or (now - self._fetched_at) > self._ttl
                or kid not in self._keys
            )
            if stale:
                try:
                    fetched = self._provider.fetch()
                except JwksError:
                    raise
                except Exception as exc:  # pragma: no cover - defensive
                    raise JwksError(f"failed to refresh JWKS: {exc}") from exc
                if not isinstance(fetched, dict):
                    raise JwksError("JWKS returned an unexpected payload")
                self._keys = fetched
                self._fetched_at = now
            key = self._keys.get(kid)
            if key is None:
                raise InvalidTokenError(f"unknown signing key: {kid}")
            return key


# ---------------------------------------------------------------------------
# Validated token
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatedToken:
    """The verified claims an endpoint is allowed to consume."""

    issuer: str
    audience: str
    idp: str  # 'auth0' | 'entra'
    external_sub: str  # the value stored in users.external_sub
    sub: str
    oid: str | None
    tid: str | None
    email: str | None
    name: str | None
    issued_at: int | None
    expires_at: int | None

    @property
    def is_entra(self) -> bool:
        return self.idp == "entra"


def entra_external_sub(oid: str, tid: str) -> str:
    """Deterministic users.external_sub for Entra: oid + tid.

    The separator is fixed and documented here so the migration and any future
    consumer build the same value.
    """

    return f"{oid}@{tid}"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class TokenValidator:
    """Validates RS256 access tokens against the configured issuers."""

    def __init__(
        self,
        issuers: Sequence[Issuer],
        *,
        providers: Mapping[str, JwksProvider] | None = None,
        clock_skew_seconds: float = 60.0,
        jwks_ttl_seconds: float = 300.0,
        now: Any = None,
    ) -> None:
        self._issuers: dict[str, Issuer] = {}
        for issuer in issuers:
            self._issuers[issuer.issuer] = issuer
        self._providers = dict(providers or {})
        self._clock_skew = clock_skew_seconds
        self._jwks_ttl = jwks_ttl_seconds
        self._now = now or time.time
        self._caches: dict[str, JwksCache] = {}

    def _unverified_claims(self, token: str) -> dict[str, Any]:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("not a JWT")
            payload = parts[1]
            padded = payload + "=" * (-len(payload) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(padded))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise InvalidTokenError("malformed token") from exc
        if not isinstance(decoded, dict):
            raise InvalidTokenError("malformed token payload")
        return decoded

    def _cache_for(self, issuer: Issuer) -> JwksCache:
        cache = self._caches.get(issuer.issuer)
        if cache is None:
            provider = self._providers.get(issuer.issuer)
            if provider is None:
                if issuer.discovery_uri is None:
                    raise JwksError("no JWKS provider configured for this issuer")
                provider = DiscoveryJwksProvider(issuer.discovery_uri)
            cache = JwksCache(provider, ttl_seconds=self._jwks_ttl, now=self._now)
            self._caches[issuer.issuer] = cache
        return cache

    def validate_access_token(self, token: str) -> ValidatedToken:
        if not token:
            raise InvalidTokenError("missing access token")

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("malformed token") from exc

        algorithm = header.get("alg")
        if algorithm != "RS256":
            # Rejects alg=none and any algorithm-confusion attempt (HS256, ...).
            raise UnsupportedAlgorithmError(
                f"unsupported signing algorithm: {algorithm}"
            )

        claims = self._unverified_claims(token)
        iss = claims.get("iss")
        if not isinstance(iss, str) or not iss:
            raise InvalidIssuerError("token is missing the 'iss' claim")

        issuer = self._issuers.get(iss)
        if issuer is None:
            raise InvalidIssuerError(f"untrusted issuer: {iss}")

        jwk = self._cache_for(issuer).get_key(header.get("kid"))
        try:
            key = RSAAlgorithm.from_jwk(jwk)
        except jwt.PyJWTError as exc:
            raise JwksError(f"could not load signing key: {exc}") from exc

        try:
            decoded = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=issuer.audience,
                issuer=issuer.issuer,
                leeway=self._clock_skew,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError("access token has expired") from exc
        except jwt.ImmatureSignatureError as exc:
            raise TokenNotYetValidError("access token is not yet valid") from exc
        except jwt.InvalidAudienceError as exc:
            raise InvalidAudienceError("access token audience does not match") from exc
        except jwt.InvalidIssuerError as exc:
            raise InvalidIssuerError("access token issuer does not match") from exc
        except jwt.MissingRequiredClaimError as exc:
            raise InvalidTokenError(f"access token is missing a required claim: {exc}") from exc
        except jwt.InvalidSignatureError as exc:
            raise InvalidTokenError("access token signature is invalid") from exc
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(f"invalid access token: {exc}") from exc

        return _map_claims(issuer, decoded)


def _map_claims(issuer: Issuer, claims: dict[str, Any]) -> ValidatedToken:
    if issuer.kind == "entra":
        oid = claims.get("oid")
        tid = claims.get("tid")
        if not isinstance(oid, str) or not oid or not isinstance(tid, str) or not tid:
            raise InvalidTokenError("Entra token is missing the 'oid' or 'tid' claim")
        external_sub = entra_external_sub(oid, tid)
        email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
        return ValidatedToken(
            issuer=issuer.issuer,
            audience=issuer.audience,
            idp="entra",
            external_sub=external_sub,
            sub=oid,
            oid=oid,
            tid=tid,
            email=_optional_str(email),
            name=_optional_str(claims.get("name")),
            issued_at=_optional_int(claims.get("iat")),
            expires_at=_optional_int(claims.get("exp")),
        )

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidTokenError("Auth0 token is missing the 'sub' claim")
    email = _optional_str(claims.get("email"))
    if email is None and issuer.email_claim:
        email = _optional_str(claims.get(issuer.email_claim))
    name = _optional_str(claims.get("name"))
    if name is None and issuer.name_claim:
        name = _optional_str(claims.get(issuer.name_claim))
    return ValidatedToken(
        issuer=issuer.issuer,
        audience=issuer.audience,
        idp="auth0",
        external_sub=sub,
        sub=sub,
        oid=None,
        tid=None,
        email=email,
        name=name,
        issued_at=_optional_int(claims.get("iat")),
        expires_at=_optional_int(claims.get("exp")),
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
