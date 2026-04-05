"""
Authentication routes: signup, login, profile.
Uses Supabase Auth for the heavy lifting; this layer creates our local User record.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import Agency, User, UserRole
from app.schemas.schemas import AuthResponse, LoginRequest, SignUpRequest, UserResponse

import httpx
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup(body: SignUpRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user + create their agency."""

    # 1. Check for existing email
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # 2. Create Supabase Auth user
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/signup",
            json={"email": body.email, "password": body.password},
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Auth provider error: " + resp.text)
        auth_data = resp.json()

    # 3. Create the agency
    slug = body.agency_name.lower().replace(" ", "-")[:100]
    agency = Agency(name=body.agency_name, slug=slug)
    db.add(agency)
    await db.flush()

    # 4. Create the local user record
    user = User(
        auth_user_id=auth_data["user"]["id"],
        email=body.email,
        full_name=body.full_name,
        role=UserRole.AGENCY_ADMIN,
        agency_id=agency.id,
        email_verified=False,
    )
    db.add(user)
    await db.flush()

    return AuthResponse(
        access_token=auth_data.get("access_token", ""),
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate via Supabase and return JWT + user profile."""

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
            json={"email": body.email, "password": body.password},
            headers={
                "apikey": settings.SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        auth_data = resp.json()

    # Load local user
    result = await db.execute(
        select(User).where(User.auth_user_id == auth_data["user"]["id"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User profile not found")

    # Update login stats
    user.login_count += 1
    from datetime import datetime
    user.last_login_at = datetime.utcnow()

    return AuthResponse(
        access_token=auth_data["access_token"],
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def get_profile(user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(user)
