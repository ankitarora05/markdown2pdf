from __future__ import annotations

import hashlib
import logging
import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Generator
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, create_engine, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DATA_DIR / 'auth.sqlite3'}"
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

JWT_SECRET = os.getenv("JWT_SECRET", "") or secrets.token_urlsafe(48)
if not os.getenv("JWT_SECRET"):
    logger.warning("JWT_SECRET is unset; sessions will be invalidated when this process restarts")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30
RESET_TOKEN_MINUTES = 30
POLICY_VERSION = "2026-10-15"
REFRESH_COOKIE = "markdown2pdf_refresh"
password_hasher = PasswordHasher()
router = APIRouter(prefix="/api/auth", tags=["authentication"])


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "auth_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_terms_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_terms_version: Mapped[str] = mapped_column(String(32), nullable=False, default=POLICY_VERSION)
    acknowledged_privacy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_cookie_policy_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RefreshSession(Base):
    __tablename__ = "auth_refresh_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PasswordReset(Base):
    __tablename__ = "auth_password_resets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("auth_users.id", ondelete="CASCADE"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CookieConsentRecord(Base):
    __tablename__ = "cookie_consent_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid4().hex)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    essential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    analytics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    advertising: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


Base.metadata.create_all(engine)
existing_user_columns = {column["name"] for column in inspect(engine).get_columns("auth_users")}
user_column_migrations = {
    "token_version": "INTEGER NOT NULL DEFAULT 0",
    "accepted_terms_version": f"VARCHAR(32) NOT NULL DEFAULT '{POLICY_VERSION}'",
    "acknowledged_privacy_at": "TIMESTAMP WITH TIME ZONE",
    "acknowledged_cookie_policy_at": "TIMESTAMP WITH TIME ZONE",
}
with engine.begin() as connection:
    for column_name, column_type in user_column_migrations.items():
        if column_name not in existing_user_columns:
            connection.execute(text(f"ALTER TABLE auth_users ADD COLUMN {column_name} {column_type}"))


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_db_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _user_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }


def _issue_access_token(user: User) -> str:
    now = _now()
    return jwt.encode(
        {
            "sub": str(user.id),
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            "jti": secrets.token_urlsafe(16),
            "type": "access",
            "ver": user.token_version,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    secure = os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", httponly=True, samesite="lax")


def _new_refresh_session(
    db: Session,
    user: User,
    family_id: str | None = None,
) -> str:
    token = secrets.token_urlsafe(48)
    db.add(
        RefreshSession(
            token_hash=_token_hash(token),
            family_id=family_id or secrets.token_urlsafe(24),
            user_id=user.id,
            expires_at=_now() + timedelta(days=REFRESH_TOKEN_DAYS),
        )
    )
    return token


def _session_response(user: User) -> dict[str, object]:
    return {
        "access_token": _issue_access_token(user),
        "token_type": "bearer",
        "user": _user_payload(user),
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


def require_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in to export your PDF")
    token = authorization[7:].strip()
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "jti", "type", "ver"]},
        )
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, TypeError, ValueError, KeyError) as error:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.") from error
    user = db.get(User, user_id)
    if user is None or payload.get("ver") != user.token_version:
        raise HTTPException(status_code=401, detail="Your account is no longer available")
    return user


def _validate_strong_password(password: str, username: str = "") -> str:
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Use 12 to 128 characters for your password.")
    if not any(character.islower() for character in password):
        raise ValueError("Add at least one lowercase letter.")
    if not any(character.isupper() for character in password):
        raise ValueError("Add at least one uppercase letter.")
    if not any(character.isdigit() for character in password):
        raise ValueError("Add at least one number.")
    if not any(not character.isalnum() for character in password):
        raise ValueError("Add at least one symbol.")
    if username and username.casefold() in password.casefold():
        raise ValueError("Your password must not contain your username.")
    return password


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=128)
    accept_terms: bool
    acknowledge_privacy: bool
    acknowledge_cookies: bool

    @field_validator("username", "first_name", "last_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required.")
        return value

    @field_validator("accept_terms")
    @classmethod
    def terms_must_be_accepted(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Please accept the terms to create an account.")
        return value

    @field_validator("acknowledge_privacy", "acknowledge_cookies")
    @classmethod
    def policies_must_be_acknowledged(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Please acknowledge the Privacy Policy and Cookie Policy to create an account.")
        return value

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        return _validate_strong_password(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def password_must_be_strong(cls, value: str) -> str:
        return _validate_strong_password(value)


@router.post("/signup")
def signup(payload: SignupRequest, response: Response, db: DbSession) -> dict[str, object]:
    try:
        _validate_strong_password(payload.password, payload.username)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    user = User(
        username=payload.username,
        username_normalized=payload.username.casefold(),
        email=str(payload.email),
        email_normalized=str(payload.email).casefold(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        password_hash=password_hasher.hash(payload.password),
        accepted_terms_at=_now(),
        accepted_terms_version=POLICY_VERSION,
        acknowledged_privacy_at=_now(),
        acknowledged_cookie_policy_at=_now(),
        created_at=_now(),
    )
    try:
        db.add(user)
        db.flush()
        refresh_token = _new_refresh_session(db, user)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That username or email address is already registered.",
        ) from error
    _set_refresh_cookie(response, refresh_token)
    return _session_response(user)


class CookieConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    essential: bool = True
    analytics: bool = False
    advertising: bool = False


@router.post("/cookie-consent")
def record_cookie_consent(payload: CookieConsentRequest, db: DbSession) -> dict[str, str | bool]:
    if not payload.essential:
        raise HTTPException(status_code=422, detail="Essential browser storage is required for this choice.")
    db.add(
        CookieConsentRecord(
            policy_version=POLICY_VERSION,
            essential=True,
            analytics=payload.analytics,
            advertising=payload.advertising,
            recorded_at=_now(),
        )
    )
    db.commit()
    return {
        "message": "Your cookie preferences have been saved.",
        "essential": True,
        "analytics": payload.analytics,
        "advertising": payload.advertising,
        "policy_version": POLICY_VERSION,
    }


@router.post("/login")
def login(payload: LoginRequest, response: Response, db: DbSession) -> dict[str, object]:
    normalized_username = payload.username.strip().casefold()
    user = db.scalar(select(User).where(User.username_normalized == normalized_username))
    valid_password = False
    if user is not None:
        try:
            valid_password = password_hasher.verify(user.password_hash, payload.password)
        except (VerifyMismatchError, InvalidHashError):
            valid_password = False
    if not valid_password or user is None:
        raise HTTPException(status_code=401, detail="Username or password is incorrect.")
    refresh_token = _new_refresh_session(db, user)
    db.commit()
    _set_refresh_cookie(response, refresh_token)
    return _session_response(user)


@router.post("/refresh", response_model=None)
def refresh_session(request: Request, response: Response, db: DbSession) -> dict[str, object] | Response:
    presented = request.cookies.get(REFRESH_COOKIE)
    if not presented:
        return Response(status_code=204)

    refresh_row = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == _token_hash(presented))
    )
    if refresh_row is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")

    if refresh_row.revoked:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == refresh_row.family_id)
            .values(revoked=True)
        )
        db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="This session is no longer valid. Please sign in again.")

    if _normalize_db_time(refresh_row.expires_at) <= _now():
        refresh_row.revoked = True
        db.commit()
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")

    user = db.get(User, refresh_row.user_id)
    if user is None:
        _clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Your account is no longer available.")
    refresh_row.revoked = True
    rotated_token = _new_refresh_session(db, user, refresh_row.family_id)
    db.commit()
    _set_refresh_cookie(response, rotated_token)
    return _session_response(user)


@router.post("/logout")
def logout(request: Request, response: Response, db: DbSession) -> dict[str, str]:
    presented = request.cookies.get(REFRESH_COOKIE)
    if presented:
        refresh_row = db.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == _token_hash(presented))
        )
        if refresh_row is not None:
            refresh_row.revoked = True
            db.commit()
    _clear_refresh_cookie(response)
    return {"message": "You have been signed out."}


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: DbSession) -> dict[str, str]:
    generic_message = "If an account matches that email, a password reset link will be sent shortly."
    user = db.scalar(
        select(User).where(User.email_normalized == str(payload.email).casefold())
    )
    if user is None:
        return {"message": generic_message}

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_from = os.getenv("SMTP_FROM", "").strip()
    if not smtp_host or not smtp_from:
        logger.warning("Password reset requested but SMTP_HOST/SMTP_FROM are not configured")
        return {"message": generic_message}

    raw_token = secrets.token_urlsafe(36)
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id)
        .values(used=True)
    )
    db.add(
        PasswordReset(
            token_hash=_token_hash(raw_token),
            user_id=user.id,
            expires_at=_now() + timedelta(minutes=RESET_TOKEN_MINUTES),
        )
    )
    db.commit()

    site_url = os.getenv("PUBLIC_SITE_URL", "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    reset_url = f"{site_url}/?reset={raw_token}"
    message = EmailMessage()
    message["Subject"] = "Reset your markdown2pdf password"
    message["From"] = smtp_from
    message["To"] = user.email
    message.set_content(
        f"Hello {user.first_name},\n\nUse this secure link within {RESET_TOKEN_MINUTES} minutes to choose a new password:\n\n{reset_url}\n\nIf you did not request this, you can ignore this email."
    )
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.ehlo()
            if os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}:
                smtp.starttls()
                smtp.ehlo()
            smtp_username = os.getenv("SMTP_USERNAME", "")
            if smtp_username:
                smtp.login(smtp_username, os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError):
        logger.exception("Could not send a password reset email")
    return {"message": generic_message}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, response: Response, db: DbSession) -> dict[str, str]:
    reset_row = db.scalar(
        select(PasswordReset).where(PasswordReset.token_hash == _token_hash(payload.token))
    )
    if (
        reset_row is None
        or reset_row.used
        or _normalize_db_time(reset_row.expires_at) <= _now()
    ):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user = db.get(User, reset_row.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")
    try:
        _validate_strong_password(payload.password, user.username)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    user.password_hash = password_hasher.hash(payload.password)
    user.token_version += 1
    db.execute(update(PasswordReset).where(PasswordReset.user_id == user.id).values(used=True))
    db.execute(update(RefreshSession).where(RefreshSession.user_id == user.id).values(revoked=True))
    db.commit()
    _clear_refresh_cookie(response)
    return {"message": "Your password has been changed. Please sign in with your new password."}
