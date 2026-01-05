"""
评论 API 路由
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin, get_optional_current_user
from app.models.user import User
from app.models.article import Article, CommentLike
from app.models.comment import Comment
from app.schemas.comment import (
    CommentCreate, CommentUpdate, CommentResponse, 
    CommentReply, CommentUser, CommentAdminItem
)
from app.schemas.common import ResponseModel, PagedData


router = APIRouter(prefix="/comments", tags=["评论"])


def build_comment_user(user: User) -> CommentUser:
    """构建评论用户信息"""
    return CommentUser(
        id=user.id,
        nickname=user.nickname or user.username,
        avatar=user.avatar
    )


def build_reply(comment: Comment, current_user_id: Optional[int] = None) -> CommentReply:
    """构建回复信息"""
    return CommentReply(
        id=comment.id,
        content=comment.content,
        user=build_comment_user(comment.user),
        reply_to=build_comment_user(comment.reply_to) if comment.reply_to else None,
        like_count=comment.like_count,
        created_at=comment.created_at,
        is_liked=False  # 后续可实现点赞功能
    )


def build_comment_response(
    comment: Comment, 
    replies: List[Comment] = None,
    current_user_id: Optional[int] = None
) -> CommentResponse:
    """构建评论响应"""
    reply_list = []
    if replies:
        reply_list = [build_reply(r, current_user_id) for r in replies]
    
    return CommentResponse(
        id=comment.id,
        content=comment.content,
        content_type=comment.content_type,
        content_id=comment.content_id,
        user=build_comment_user(comment.user),
        like_count=comment.like_count,
        created_at=comment.created_at,
        is_liked=False,
        replies=reply_list,
        reply_count=len(reply_list)
    )


@router.post("", response_model=ResponseModel)
def create_comment(
    comment_in: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建评论（需登录）- 支持多种内容类型"""
    # 验证内容类型
    valid_content_types = ["article", "changelog", "message_board"]
    if comment_in.content_type not in valid_content_types:
        return ResponseModel(code=400, msg="无效的内容类型")
    
    # 如果是文章评论，验证文章存在
    article = None
    if comment_in.content_type == "article":
        article = db.query(Article).filter(Article.id == comment_in.content_id).first()
        if not article:
            return ResponseModel(code=404, msg="文章不存在")
    
    # 验证父评论（如果是回复）
    if comment_in.parent_id:
        parent_comment = db.query(Comment).filter(Comment.id == comment_in.parent_id).first()
        if not parent_comment:
            return ResponseModel(code=404, msg="父评论不存在")
        # 确保回复的是同一内容的评论
        if parent_comment.content_type != comment_in.content_type or parent_comment.content_id != comment_in.content_id:
            return ResponseModel(code=400, msg="不能跨内容回复评论")
    
    # 创建评论
    comment = Comment(
        content=comment_in.content,
        content_type=comment_in.content_type,
        content_id=comment_in.content_id,
        user_id=current_user.id,
        parent_id=comment_in.parent_id,
        reply_to_id=comment_in.reply_to_id
    )
    
    db.add(comment)
    
    # 更新文章评论数（仅针对文章类型）
    if article:
        article.comment_count += 1
    
    db.commit()
    db.refresh(comment)
    
    return ResponseModel(
        code=200, 
        msg="评论成功",
        data={"id": comment.id}
    )


# ============ 管理员接口 ============

@router.get("/admin/list", response_model=ResponseModel)
def get_admin_comments(
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    is_approved: Optional[bool] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取评论列表（管理员）"""
    # 基础查询 - 先不加 joinedload
    base_query = db.query(Comment)
    
    if is_approved is not None:
        base_query = base_query.filter(Comment.is_approved == is_approved)
    
    if keyword:
        base_query = base_query.filter(Comment.content.contains(keyword))
    
    # 先获取总数
    total = base_query.count()
    
    # 再加 joinedload 并分页
    comments = base_query.options(
        joinedload(Comment.user)
    ).order_by(Comment.created_at.desc()).offset((current - 1) * size).limit(size).all()
    
    # 获取相关文章信息
    article_ids = [c.content_id for c in comments if c.content_type == 'article']
    articles = {}
    if article_ids:
        article_list = db.query(Article).filter(Article.id.in_(article_ids)).all()
        articles = {a.id: a for a in article_list}

    records = []
    for comment in comments:
        article_title = "未知来源"
        if comment.content_type == 'article':
            article = articles.get(comment.content_id)
            article_title = article.title if article else "文章已删除"
        elif comment.content_type == 'changelog':
            article_title = "更新日志"
        elif comment.content_type == 'message_board':
            article_title = "留言板"

        records.append(CommentAdminItem(
            id=comment.id,
            content=comment.content,
            article_id=comment.content_id,
            article_title=article_title,
            user=build_comment_user(comment.user),
            is_approved=comment.is_approved,
            created_at=comment.created_at
        ))
    
    return ResponseModel(
        code=200,
        data=PagedData(
            records=records,
            total=total,
            current=current,
            size=size
        )
    )


@router.get("/{content_type}/{content_id}", response_model=ResponseModel)
def get_comments_by_content(
    content_type: str,
    content_id: int,
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """获取指定内容的评论列表（分页，包含嵌套回复）"""
    # 验证内容类型
    valid_content_types = ["article", "changelog", "message_board"]
    if content_type not in valid_content_types:
        return ResponseModel(code=400, msg="无效的内容类型")
    
    # 如果是文章评论，验证文章存在
    if content_type == "article":
        article = db.query(Article).filter(Article.id == content_id).first()
        if not article:
            return ResponseModel(code=404, msg="文章不存在")
    
    current_user_id = current_user.id if current_user else None
    
    # 获取顶级评论（parent_id 为 None 的）
    query = db.query(Comment).filter(
        and_(
            Comment.content_type == content_type,
            Comment.content_id == content_id,
            Comment.parent_id == None,
            Comment.is_approved == True
        )
    ).options(
        joinedload(Comment.user)
    ).order_by(Comment.created_at.desc())
    
    total = query.count()
    top_comments = query.offset((current - 1) * size).limit(size).all()
    
    # 获取所有回复
    comment_ids = [c.id for c in top_comments]
    replies_query = db.query(Comment).filter(
        and_(
            Comment.parent_id.in_(comment_ids),
            Comment.is_approved == True
        )
    ).options(
        joinedload(Comment.user),
        joinedload(Comment.reply_to)
    ).order_by(Comment.created_at.asc())
    
    all_replies = replies_query.all()
    
    # 按父评论ID分组
    replies_map = {}
    for reply in all_replies:
        if reply.parent_id not in replies_map:
            replies_map[reply.parent_id] = []
        replies_map[reply.parent_id].append(reply)
    
    # 构建响应
    records = []
    for comment in top_comments:
        replies = replies_map.get(comment.id, [])
        records.append(build_comment_response(comment, replies, current_user_id))
    
    return ResponseModel(
        code=200,
        data=PagedData(
            records=records,
            total=total,
            current=current,
            size=size
        )
    )


@router.delete("/{comment_id}", response_model=ResponseModel)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除评论（只能删除自己的评论，管理员可删除任何评论）"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return ResponseModel(code=404, msg="评论不存在")
    
    # 权限检查
    if comment.user_id != current_user.id and current_user.role != "admin":
        return ResponseModel(code=403, msg="无权删除此评论")
    
    # 获取文章以更新评论数
    article = None
    if comment.content_type == 'article':
        article = db.query(Article).filter(Article.id == comment.content_id).first()
    
    # 计算要删除的评论数（包括子评论）
    child_count = db.query(Comment).filter(Comment.parent_id == comment_id).count()
    
    db.delete(comment)
    
    # 更新文章评论数
    if article:
        article.comment_count = max(0, article.comment_count - 1 - child_count)
    
    db.commit()
    
    return ResponseModel(code=200, msg="删除成功")


@router.post("/{comment_id}/like", response_model=ResponseModel)
def like_comment(
    comment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user)
):
    """点赞评论（防止重复点赞）"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return ResponseModel(code=404, msg="评论不存在")
    
    # 获取客户端 IP
    client_ip = request.client.host if request.client else None
    
    # 检查是否已点赞
    like_query = db.query(CommentLike).filter(CommentLike.comment_id == comment_id)
    
    if current_user:
        existing_like = like_query.filter(CommentLike.user_id == current_user.id).first()
    else:
        if not client_ip:
            return ResponseModel(code=400, msg="无法获取客户端信息")
        existing_like = like_query.filter(
            CommentLike.user_id == None,
            CommentLike.ip_address == client_ip
        ).first()
    
    if existing_like:
        return ResponseModel(code=400, msg="您已经点过赞了")
    
    # 创建点赞记录
    new_like = CommentLike(
        comment_id=comment_id,
        user_id=current_user.id if current_user else None,
        ip_address=client_ip
    )
    db.add(new_like)
    
    comment.like_count += 1
    db.commit()
    
    return ResponseModel(code=200, msg="点赞成功", data={"like_count": comment.like_count})


@router.put("/admin/{comment_id}", response_model=ResponseModel)
def update_comment_admin(
    comment_id: int,
    comment_in: CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新评论状态（管理员）"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return ResponseModel(code=404, msg="评论不存在")
    
    if comment_in.content is not None:
        comment.content = comment_in.content
    if comment_in.is_approved is not None:
        comment.is_approved = comment_in.is_approved
    
    db.commit()
    
    return ResponseModel(code=200, msg="更新成功")


@router.delete("/admin/{comment_id}", response_model=ResponseModel)
def delete_comment_admin(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除评论（管理员）"""
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return ResponseModel(code=404, msg="评论不存在")
    
    # 获取文章以更新评论数
    article = None
    if comment.content_type == 'article':
        article = db.query(Article).filter(Article.id == comment.content_id).first()
    
    # 计算要删除的评论数
    child_count = db.query(Comment).filter(Comment.parent_id == comment_id).count()
    
    db.delete(comment)
    
    if article:
        article.comment_count = max(0, article.comment_count - 1 - child_count)
    
    db.commit()
    
    return ResponseModel(code=200, msg="删除成功")
