
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from database import Base


# 1. OJT USERS
class OJTUser(Base):
    __tablename__ = "ojt_users"

    username = Column(String(50), primary_key=True)
    password_hash = Column(String(255), nullable=False)


# 2. PC USERS
class PCUser(Base):
    __tablename__ = "PC_Users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    computer_username = Column(String(100), nullable=False)


# 3. COMPUTERS
class Computer(Base):
    __tablename__ = "computers"

    computer_id = Column(Integer, primary_key=True, autoincrement=True)
    computer_name = Column(String(50), nullable=False)
    ip_address = Column(String(45))
    mac_address = Column(String(17))
    status = Column(String(30))
    computer_uuid = Column(String(36))


# 4. MONITORING AGENTS
class MonitoringAgent(Base):
    __tablename__ = "monitoring_agents"

    agent_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_version = Column(String(30))
    agent_status = Column(String(30))
    last_heartbeat_at = Column(DateTime)
    computer_id = Column(
        Integer,
        ForeignKey("computers.computer_id"),
        nullable=False
    )


# 5. DISCONNECTION LOGS
class DisconnectionLog(Base):
    __tablename__ = "disconnection_logs"

    disconnection_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Integer,
        ForeignKey("monitoring_agents.agent_id"),
        nullable=False
    )
    disconnection_time = Column(DateTime)
    last_heartbeat_at = Column(DateTime)
    disconnection_type = Column(String(50))


# 6. LOGIN SESSIONS
class LoginSession(Base):
    __tablename__ = "login_sessions"

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Integer,
        ForeignKey("monitoring_agents.agent_id"),
        nullable=False
    )
    user_id = Column(
        Integer,
        ForeignKey("PC_Users.user_id"),
        nullable=False
    )
    disconnection_id = Column(
        Integer,
        ForeignKey("disconnection_logs.disconnection_id"),
        nullable=True
    )
    login_time = Column(DateTime)
    logout_time = Column(DateTime)
    session_status = Column(String(30))


# 7. APPLICATION USAGE
class ApplicationUsage(Base):
    __tablename__ = "application_usage"

    usage_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("login_sessions.session_id"),
        nullable=False
    )
    application_name = Column(String(100))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_time = Column(Integer)
