from typing import Annotated

from pydantic import BaseModel, EmailStr, StringConstraints

PasswordStr = Annotated[str, StringConstraints(min_length=8, max_length=72)]
NameStr = Annotated[str, StringConstraints(min_length=1, max_length=50, pattern=r"^[A-Za-z\s\-]+$")]
PhoneStr = Annotated[str, StringConstraints(min_length=7, max_length=20)]


class LoginRequest(BaseModel):
    email: EmailStr
    password: PasswordStr


class RegisterRequest(LoginRequest):
    first_name: NameStr
    middle_name: NameStr | None = None
    last_name: NameStr
    phone_number: PhoneStr | None = None
    role_id: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    role_id: int
    is_active: bool
    has_assignments: bool = False
    is_demo: bool = False  # DEMO FEATURE: remove this line if demo mode is retired

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


# --- User Management ---------------------------------------------------------
class UserUpdateRequest(BaseModel):
    first_name: NameStr | None = None
    middle_name: NameStr | None = None
    last_name: NameStr | None = None
    phone_number: PhoneStr | None = None


class PasswordChangeRequest(BaseModel):
    current_password: PasswordStr
    new_password: PasswordStr


class PasswordResetRequest(BaseModel):
    new_password: PasswordStr
