from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

class ProductData(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    sku: str
    title: str
    url: str
    current_price: float
    original_price: Optional[float] = None
    currency: str = "USD"
    description: Optional[str] = None
    scraped_at: datetime = datetime.utcnow()