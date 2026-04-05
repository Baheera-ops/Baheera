"""
FastAPI dependencies for authentication and multi-tenant scoping.
Validates Supabase JWT tokens and resolves the current user + agency.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import Agent, User, UserRole

settings = get_settings()
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Validate the Supabase JWT and return the corresponding User.
    Every authenticated endpoint depends on this.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        auth_user_id = payload.get("sub")
        if not auth_user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(
        select(User).where(User.auth_user_id == auth_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    return user


async def get_current_agency_id(
    user: User = Depends(get_current_user),
) -> str:
    """Extract the agency_id from the authenticated user for tenant scoping."""
    if not user.agency_id:
        raise HTTPException(status_code=403, detail="User not associated with any agency")
    return str(user.agency_id)


def require_role(*roles: UserRole):
    """Factory for role-based access control dependencies."""
    async def _check_role(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {[r.value for r in roles]}",
            )
        return user
    return _check_role


# Convenience shortcuts
require_admin = require_role(UserRole.AGENCY_ADMIN, UserRole.SUPER_ADMIN)
require_agent_or_admin = require_role(UserRole.AGENT, UserRole.AGENCY_ADMIN, UserRole.SUPER_ADMIN)
