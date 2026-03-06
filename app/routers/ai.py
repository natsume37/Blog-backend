import logging

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.deps import get_current_admin
from app.models.user import User
from app.schemas.ai import AIDraftRequest, AIDraftResponse
from app.schemas.common import ResponseModel
from app.services.ai_article import generate_article_draft


router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)


@router.post("/article-draft", response_model=ResponseModel[AIDraftResponse])
def create_article_draft(
    payload: AIDraftRequest,
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    """生成文章草稿（管理员）"""
    try:
        data = generate_article_draft(payload, settings)
        if not data.get("content_markdown"):
            return ResponseModel(code=502, msg="AI 返回内容为空")
        return ResponseModel(code=200, msg="生成成功", data=AIDraftResponse(**data))
    except Exception as exc:
        logger.error("Generate AI draft failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg="AI 草稿生成失败，请稍后重试")
