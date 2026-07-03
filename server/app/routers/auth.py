from fastapi import APIRouter
from app.core.security import auth_backend, fastapi_users
from app.schemas.user import UserRead, UserCreate, UserUpdate

router = APIRouter()

# login and logout endpoints
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)

# registration endpoint
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# current user profile (used by frontend to verify token)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"],
)
