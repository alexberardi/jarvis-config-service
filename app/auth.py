import hmac

from fastapi import Header, HTTPException, status
from app.config import get_settings, is_placeholder_token


async def require_admin(x_admin_token: str = Header(...)) -> bool:
    """Dependency that requires admin token for write operations."""
    settings = get_settings()

    if not settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin token not configured on server"
        )

    # A publicly-known template placeholder must never authenticate, even if
    # the server itself was left configured with one.
    if is_placeholder_token(x_admin_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )

    # Constant-time compare so the token can't be recovered byte-by-byte via
    # response timing.
    if not hmac.compare_digest(x_admin_token, settings.ADMIN_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )

    return True
