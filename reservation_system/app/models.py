# models.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'provider', 'patient', or 'admin'

    appointment_slots = relationship("AppointmentSlot", back_populates="provider")


class AppointmentSlot(Base):
    __tablename__ = 'appointment_slots'
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default='available')
    client_id = Column(Integer, nullable=True)
    reserved_by = Column(Integer, nullable=True)  # Field for reservation
    reserved_until = Column(DateTime, nullable=True)  # Field for reservation expiry
    confirmed = Column(Boolean, nullable=False, default=False)  # New field to indicate confirmation status

    provider = relationship("User", back_populates="appointment_slots")

    __table_args__ = (
        UniqueConstraint('provider_id', 'start_time', name='_provider_start_time_uc'),
        Index('idx_provider_start_time', 'provider_id', 'start_time'),
    )
