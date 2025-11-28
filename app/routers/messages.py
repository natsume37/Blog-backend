from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.message import Message
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.common import ResponseModel, PagedData


router = APIRouter(prefix="/messages", tags=["留言"])


@router.get("", response_model=ResponseModel[PagedData[MessageResponse]])
def get_messages(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取留言列表"""
    query = db.query(Message).order_by(Message.created_at.desc())
    
    total = query.count()
    messages = query.offset((current - 1) * size).limit(size).all()
    
    records = [MessageResponse(
        id=m.id,
        content=m.content,
        nickname=m.nickname,
        avatar=m.avatar,
        email=m.email,
        created_at=m.created_at,
        parent_id=m.parent_id
    ) for m in messages]
    
    return ResponseModel(
        code=200,
        data=PagedData(
            records=records,
            total=total,
            current=current,
            size=size
        )
    )


@router.post("", response_model=ResponseModel)
def create_message(
    message_data: MessageCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """发布留言"""
    try:
        # Get IP address
        ip_address = request.client.host if request.client else ""
        
        message = Message(
            content=message_data.content,
            nickname=message_data.nickname or "游客",
            avatar=message_data.avatar or "",
            email=message_data.email or "",
            ip_address=ip_address,
            parent_id=message_data.parent_id
        )
        db.add(message)
        db.commit()
        
        return ResponseModel(code=200, msg="留言成功")
    except Exception as e:
        db.rollback()
        return ResponseModel(code=500, msg=f"留言失败: {str(e)}")
