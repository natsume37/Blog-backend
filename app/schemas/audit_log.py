from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: str = ""
    action: str = ""
    target_type: str = ""
    target_id: Optional[str] = ""
    description: Optional[str] = ""
    request_path: Optional[str] = ""
    request_method: Optional[str] = ""
    ip: Optional[str] = ""
    user_agent: Optional[str] = ""
    extra: Optional[str] = ""
    created_at: datetime

    model_config = {"from_attributes": True}
