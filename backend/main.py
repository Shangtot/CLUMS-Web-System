import os
import hashlib
import hmac
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models import (
    OJTUser,
    PCUser,
    Computer,
    MonitoringAgent,
    LoginSession,
    ApplicationUsage,
    DisconnectionLog,
)


app = FastAPI(
    title="CLUMS Backend",
    description="Computer Laboratory User Monitoring System",
    version="1.0.0",
)


# -------------------------------------------------------------------
# CONFIGURATION
# database.py loads backend/.env when it is imported.
# -------------------------------------------------------------------

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is missing from backend/.env")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# -------------------------------------------------------------------
# REQUEST MODELS
# -------------------------------------------------------------------

class HeartbeatRequest(BaseModel):
    agent_id: int
    computer_id: int
    agent_version: str | None = None


class StudentLoginRequest(BaseModel):
    agent_id: int
    user_id: int


class StudentLogoutRequest(BaseModel):
    session_id: int


class ApplicationUsageRequest(BaseModel):
    session_id: int
    application_name: str
    start_time: datetime
    end_time: datetime


class DisconnectionRequest(BaseModel):
    agent_id: int
    disconnection_type: str
    last_heartbeat_at: datetime | None = None


# -------------------------------------------------------------------
# GENERAL / HEALTH
# -------------------------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Welcome to CLUMS Backend!",
        "status": "running",
    }


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "system": "CLUMS",
            "database": "connected",
        }
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable",
        )


# -------------------------------------------------------------------
# MONITORING AGENT HEARTBEAT
# NOTE: Agent API-key authentication is not implemented yet.
# -------------------------------------------------------------------

@app.post("/api/agents/heartbeat")
def agent_heartbeat(
    request: HeartbeatRequest,
    db: Session = Depends(get_db),
):
    agent = (
        db.query(MonitoringAgent)
        .filter(
            MonitoringAgent.agent_id == request.agent_id,
            MonitoringAgent.computer_id == request.computer_id,
        )
        .first()
    )

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Monitoring agent not found or computer assignment does not match",
        )

    computer = (
        db.query(Computer)
        .filter(Computer.computer_id == request.computer_id)
        .first()
    )

    if not computer:
        raise HTTPException(status_code=404, detail="Computer not found")

    heartbeat_time = datetime.now(timezone.utc).replace(tzinfo=None)

    agent.agent_status = "online"
    agent.last_heartbeat_at = heartbeat_time
    computer.status = "online"

    if request.agent_version:
        agent.agent_version = request.agent_version

    db.commit()

    return {
        "message": "Heartbeat received successfully",
        "agent_id": agent.agent_id,
        "computer_id": computer.computer_id,
        "agent_status": agent.agent_status,
        "computer_status": computer.status,
        "last_heartbeat_at": heartbeat_time.isoformat(),
    }


# -------------------------------------------------------------------
# STUDENT LOGIN / LOGOUT
# NOTE: These endpoints also need Agent authentication before deployment.
# -------------------------------------------------------------------

@app.post("/api/sessions/login")
def student_login(
    request: StudentLoginRequest,
    db: Session = Depends(get_db),
):
    agent = (
        db.query(MonitoringAgent)
        .filter(MonitoringAgent.agent_id == request.agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Monitoring agent not found")

    student = (
        db.query(PCUser)
        .filter(PCUser.user_id == request.user_id)
        .first()
    )
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    new_session = LoginSession(
        agent_id=agent.agent_id,
        user_id=student.user_id,
        login_time=datetime.now(timezone.utc).replace(tzinfo=None),
        session_status="active",
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return {
        "message": "Student login recorded successfully",
        "session_id": new_session.session_id,
        "agent_id": new_session.agent_id,
        "user_id": new_session.user_id,
        "login_time": new_session.login_time.isoformat(),
        "session_status": new_session.session_status,
    }


@app.post("/api/sessions/logout")
def student_logout(
    request: StudentLogoutRequest,
    db: Session = Depends(get_db),
):
    student_session = (
        db.query(LoginSession)
        .filter(
            LoginSession.session_id == request.session_id,
            LoginSession.session_status == "active",
        )
        .first()
    )

    if not student_session:
        raise HTTPException(
            status_code=404,
            detail="Active student session not found",
        )

    logout_time = datetime.now(timezone.utc).replace(tzinfo=None)
    student_session.logout_time = logout_time
    student_session.session_status = "completed"

    db.commit()

    return {
        "message": "Student logout recorded successfully",
        "session_id": student_session.session_id,
        "logout_time": logout_time.isoformat(),
        "session_status": student_session.session_status,
    }


# -------------------------------------------------------------------
# APPLICATION USAGE
# -------------------------------------------------------------------

@app.post("/api/activities/application")
def record_application_usage(
    request: ApplicationUsageRequest,
    db: Session = Depends(get_db),
):
    student_session = (
        db.query(LoginSession)
        .filter(LoginSession.session_id == request.session_id)
        .first()
    )

    if not student_session:
        raise HTTPException(status_code=404, detail="Student session not found")

    if student_session.session_status != "active":
        raise HTTPException(
            status_code=400,
            detail="Application usage requires an active student session",
        )

    application_name = request.application_name.strip()
    if not application_name:
        raise HTTPException(
            status_code=400,
            detail="Application name cannot be empty",
        )

    if request.end_time < request.start_time:
        raise HTTPException(
            status_code=400,
            detail="End time cannot be earlier than start time",
        )

    duration_minutes = int(
        (request.end_time - request.start_time).total_seconds() // 60
    )

    activity = ApplicationUsage(
        session_id=student_session.session_id,
        application_name=application_name,
        start_time=request.start_time,
        end_time=request.end_time,
        duration_time=duration_minutes,
    )

    db.add(activity)
    db.commit()
    db.refresh(activity)

    return {
        "message": "Application usage recorded successfully",
        "usage_id": activity.usage_id,
        "session_id": activity.session_id,
        "application_name": activity.application_name,
        "duration_minutes": activity.duration_time,
    }


# -------------------------------------------------------------------
# SHUTDOWN / RESTART / UNEXPECTED DISCONNECTION
# -------------------------------------------------------------------

@app.post("/api/system-events")
def record_disconnection(
    request: DisconnectionRequest,
    db: Session = Depends(get_db),
):
    allowed_types = {
        "shutdown",
        "restart",
        "unexpected_disconnection",
    }

    event_type = request.disconnection_type.strip().lower()
    if event_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid disconnection type",
        )

    agent = (
        db.query(MonitoringAgent)
        .filter(MonitoringAgent.agent_id == request.agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Monitoring agent not found",
        )

    disconnection_time = datetime.now(timezone.utc).replace(tzinfo=None)

    log = DisconnectionLog(
        agent_id=agent.agent_id,
        disconnection_time=disconnection_time,
        last_heartbeat_at=request.last_heartbeat_at,
        disconnection_type=event_type,
    )

    agent.agent_status = "offline"

    computer = (
        db.query(Computer)
        .filter(Computer.computer_id == agent.computer_id)
        .first()
    )
    if computer:
        computer.status = "offline"

    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "message": "Disconnection recorded successfully",
        "disconnection_id": log.disconnection_id,
        "agent_id": log.agent_id,
        "disconnection_type": log.disconnection_type,
        "disconnection_time": log.disconnection_time.isoformat(),
        "agent_status": agent.agent_status,
    }


# -------------------------------------------------------------------
# ADMINISTRATOR PASSWORD VERIFICATION / JWT
# Stored password format:
# pbkdf2_sha256$iterations$salt$hex_digest
# -------------------------------------------------------------------

def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected_hash = stored_hash.split("$")

        if algorithm != "pbkdf2_sha256":
            return False

        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()

        return hmac.compare_digest(calculated_hash, expected_hash)
    except (ValueError, TypeError, AttributeError):
        return False


@app.post("/api/auth/login")
def admin_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    admin = (
        db.query(OJTUser)
        .filter(OJTUser.username == form_data.username)
        .first()
    )

    if not admin or not verify_password(
        form_data.password,
        admin.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    expiration = datetime.now(timezone.utc) + timedelta(
        minutes=TOKEN_EXPIRE_MINUTES
    )

    token = jwt.encode(
        {
            "sub": admin.username,
            "exp": expiration,
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

    return {
        "message": "Administrator login successful",
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": TOKEN_EXPIRE_MINUTES,
    }


def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        username = payload.get("sub")

        if not username:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication token",
            )

    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    admin = (
        db.query(OJTUser)
        .filter(OJTUser.username == username)
        .first()
    )

    if not admin:
        raise HTTPException(
            status_code=401,
            detail="Administrator account not found",
        )

    return admin


@app.get("/api/auth/me")
def get_admin_profile(
    current_admin: OJTUser = Depends(get_current_admin),
):
    return {
        "username": current_admin.username,
        "role": "Administrator",
    }
