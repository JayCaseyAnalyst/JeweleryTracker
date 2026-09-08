import uuid
from datetime import datetime
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from config import DATABASE_URL

Base = declarative_base()

class Product(Base):
    __tablename__ = 'products'

    sku = Column(String(50), primary_key=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # One-to-many relationship tracking price snapshots over time
    price_snapshots = relationship(
        "PriceSnapshot", 
        back_populates="product", 
        cascade="all, delete-orphan"
    )

class PriceSnapshot(Base):
    __tablename__ = 'price_snapshots'

    # Native PostgreSQL UUID primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku = Column(String(50), ForeignKey('products.sku', ondelete='CASCADE'), nullable=False)
    
    # Using Numeric/Decimal for exact currency precision instead of Float
    price = Column(Numeric(precision=10, scale=2), nullable=False)
    original_price = Column(Numeric(precision=10, scale=2), nullable=True)
    currency = Column(String(3), default="USD", nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    product = relationship("Product", back_populates="price_snapshots")

    # Index for fast time-series analytical queries (e.g., historical price trends for a SKU)
    __table_args__ = (
        Index('idx_snapshot_sku_recorded_at', 'sku', recorded_at.desc()),
    )

def init_db():
    """Initializes schema in the target PostgreSQL instance."""
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)