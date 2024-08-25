from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timedelta

from sqlalchemy.orm import relationship

Base = declarative_base()


class Provider(Base):
    __tablename__ = 'providers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)

    # One-to-many relationship with AppointmentSlot
    appointment_slots = relationship("AppointmentSlot", back_populates="provider")

class AppointmentSlot(Base):
    __tablename__ = 'appointment_slots'
    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default='available')
    client_id = Column(Integer, nullable=True)

    provider = relationship("Provider", back_populates="appointment_slots")


class Reservation(Base):
    __tablename__ = 'reservations'
    id = Column(Integer, primary_key=True, index=True)
    appointment_slot_id = Column(Integer, ForeignKey('appointment_slots.id'), nullable=False, index=True)
    client_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=30))
    status = Column(String, nullable=False, default='pending')

    __table_args__ = (
        Index('idx_appointment_slot_status', 'appointment_slot_id', 'status'),
    )
