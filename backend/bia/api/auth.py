import base64
import binascii
import logging
import secrets
from enum import StrEnum

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_AUTHORIZATION_HEADER = "Authorization"
_CHALLENGE_HEADER = "WWW-Authenticate"
_BASIC_SCHEME = "basic"
_CHALLENGE_VALUE = 'Basic realm="Bia Agent Platform"'


class PublicPath(StrEnum):
    """The only paths reachable without credentials.

    Exists as an explicit allow-list so every other path, including future routers and
    Swagger, is protected by default. Consumed by `BasicAuthMiddleware` and by
    `bia/api/main.py` to declare the routes.
    """

    HEALTH = "/health"


def _extract_password(authorization: str) -> bytes | None:
    """Extracts the password from an HTTP Basic `Authorization` header value.

    Exists to keep header parsing apart from the access decision; used by
    `BasicAuthMiddleware`.

    Args:
        authorization: The raw value of the `Authorization` header.

    Returns:
        bytes | None: the password, or None if the header is not valid HTTP Basic.
    """
    scheme, _, encoded_credentials = authorization.partition(" ")
    if scheme.lower() != _BASIC_SCHEME:
        return None
    try:
        credentials = base64.b64decode(encoded_credentials, validate=True)
    except binascii.Error:
        return None
    _, separator, password = credentials.partition(b":")
    return password if separator else None


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Requires the shared password on every request outside the public allow-list.

    Exists because the API and Swagger are deployed on a public URL and some endpoints
    spend OpenAI quota. Works as middleware so a new route cannot forget to be protected.
    The username is ignored: there is one shared credential, not user accounts. Registered
    on the application by `bia/api/main.py`.
    """

    def __init__(self, app: ASGIApp, password: str) -> None:
        """Initializes the middleware with the password to enforce.

        Args:
            app (ASGIApp): The wrapped ASGI application.
            password (str): The shared password that grants access.
        """
        super().__init__(app)
        self._password = password.encode()

    def _is_authorized(self, request: Request) -> bool:
        """Checks whether a request carries the shared password.

        Exists to isolate the credential comparison, done in constant time so response
        timing does not reveal the password; used by `dispatch`.

        Args:
            request: The incoming HTTP request.

        Returns:
            bool: True if the request presents the correct password.
        """
        provided = _extract_password(request.headers.get(_AUTHORIZATION_HEADER, ""))
        return provided is not None and secrets.compare_digest(provided, self._password)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Forwards authorized and public requests, and rejects the rest.

        Exists as the single access checkpoint of the API; called by Starlette on every
        request.

        Args:
            request: The incoming HTTP request.
            call_next: The next handler in the application stack.

        Returns:
            Response: the application's response, or a 401 that makes browsers prompt for
            credentials.
        """
        if request.url.path in set(PublicPath) or self._is_authorized(request):
            return await call_next(request)
        logger.warning("Rejected unauthenticated request to %s", request.url.path)
        return Response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={_CHALLENGE_HEADER: _CHALLENGE_VALUE},
        )
