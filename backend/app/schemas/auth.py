from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ApiModel, Name

Role = Literal["teacher", "student"]


def _password_rules(v: str) -> str:
    if len(v.encode("utf-8")) > 72:
        raise ValueError("must be at most 72 bytes")
    if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("must contain at least one letter and one number")
    return v


class RegisterIn(ApiModel):
    name: Name
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: Role
    invite_code: str | None = Field(default=None, max_length=100)

    _pw = field_validator("password")(_password_rules)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: Role
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class SessionRenewedOut(BaseModel):
    """Returned when every earlier session was revoked: a fresh token for the device that made the request."""
    detail: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ProfileUpdate(ApiModel):
    name: Name


class PasswordChange(ApiModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)

    _pw = field_validator("new_password")(_password_rules)


class StudentBrief(BaseModel):
    id: str
    name: str
    email: str
