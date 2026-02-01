from fastapi import Header, HTTPException, status
from app.config import get_settings


async def require_admin(x_admin_token: str = Header(...)) -> bool:
    """Dependency that requires admin token for write operations."""
    settings = get_settings()
    
    if not settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin token not configured on server"
        )
    
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )
    
    return True
