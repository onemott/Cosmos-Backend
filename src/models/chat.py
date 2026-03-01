from typing import Optional, TYPE_CHECKING
from uuid import uuid4
from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base, TimestampMixin, UUID

if TYPE_CHECKING:
    from src.models.client import Client
    from src.models.user import User
    from src.models.client_user import ClientUser


class ChatSession(Base, TimestampMixin):
    """聊天会话模型"""
    __tablename__ = "chat_sessions"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active") # active, archived
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    client: Mapped["Client"] = relationship("Client", back_populates="chat_sessions")
    members: Mapped[list["ChatSessionMember"]] = relationship("ChatSessionMember", back_populates="session", cascade="all, delete-orphan")
    messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="session", order_by="desc(ChatMessage.created_at)", cascade="all, delete-orphan")


class ChatSessionMember(Base, TimestampMixin):
    """会话成员模型 - 记录谁在会话里"""
    __tablename__ = "chat_session_members"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    
    # 多态关联：User (Admin) 或 ClientUser (App)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    client_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("client_users.id"), nullable=True)
    
    user_type: Mapped[str] = mapped_column(String(20)) # "user" or "client_user"
    last_read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True) #以此时间点判断未读数
    
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="members")
    user: Mapped[Optional["User"]] = relationship("User")
    client_user: Mapped[Optional["ClientUser"]] = relationship("ClientUser")


class ChatMessage(Base, TimestampMixin):
    """聊天消息模型"""
    __tablename__ = "chat_messages"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), nullable=False, index=True)
    
    # 客户端生成的ID，用于去重
    client_side_id: Mapped[Optional[str]] = mapped_column(String(36), unique=True, nullable=True)
    
    # 发送者
    sender_type: Mapped[str] = mapped_column(String(20)) # "user", "client_user", "system"
    sender_id: Mapped[str] = mapped_column(String(36)) 
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text") # text, image, file
    
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
