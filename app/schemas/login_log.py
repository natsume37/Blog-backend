from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LoginLogItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: str = ""
    ip: str = ""
    user_agent: str = ""
    success: bool
    reason: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}
