from typing import Optional, List
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user_optional
from app.core.cache import redis_client
from app.models.article import Article, Category, Tag, article_tags, ArticleLike
from app.models.user import User
from app.schemas.article import (
    ArticleListItem, ArticleDetail, CategoryResponse, TagResponse,
    ArticleCreate, ArticleUpdate, ArticleAdminListItem, CategoryWithArticles
)
from app.schemas.common import ResponseModel, PagedData
from app.utils.qiniu import strip_qiniu_params, refresh_qiniu_params_in_content
from app.core.config import get_settings, Settings


router = APIRouter(prefix="/articles", tags=["文章"])
logger = logging.getLogger(__name__)


@router.get("/admin/list", response_model=ResponseModel[PagedData[ArticleAdminListItem]])
def get_admin_articles(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings)
):
    """获取文章列表 (管理员 - 包含草稿)"""
    query = db.query(Article)
    
    if keyword:
        query = query.filter(Article.title.contains(keyword))
        
    query = query.order_by(Article.created_at.desc())
    
    total = query.count()
    articles = query.offset((current - 1) * size).limit(size).all()
    
    # 获取七牛配置
    qiniu_domain = settings.QINIU_DOMAIN
    timestamp_key = settings.QINIU_TIMESTAMP_KEY
    expire = settings.QINIU_TIMESTAMP_EXPIRE
    
    records = []
    for article in articles:
        category_name = article.category.name if article.category else ""
        
        # 刷新 cover 中的签名链接
        cover = article.cover
        if settings.is_qiniu_timestamp_enabled and cover:
            cover = refresh_qiniu_params_in_content(cover, qiniu_domain, timestamp_key, expire)
            
        records.append(ArticleAdminListItem(
            id=article.id,
            title=article.title,
            summary=article.summary or "",
            cover=cover or "",
            createTime=article.created_at.strftime("%Y-%m-%d %H:%M:%S") if article.created_at else "",
            categoryName=category_name,
            viewCount=article.view_count,
            commentCount=article.comment_count,
            likeCount=article.like_count,
            is_published=article.is_published,
            is_top=article.is_top,
            is_recommend=article.is_recommend,
            is_protected=bool(article.is_protected or False)
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


@router.post("", response_model=ResponseModel)
def create_article(
    article_in: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings)
):
    """创建文章 (管理员)"""
    # Check category
    if article_in.category_id:
        category = db.query(Category).filter(Category.id == article_in.category_id).first()
        if not category:
            return ResponseModel(code=404, msg="分类不存在")
    
    # 剥离七牛云签名的逻辑
    content = article_in.content
    cover = article_in.cover
    if settings.is_qiniu_timestamp_enabled:
        content = strip_qiniu_params(content, settings.QINIU_DOMAIN)
        if cover:
            cover = strip_qiniu_params(cover, settings.QINIU_DOMAIN)
            
    article = Article(
        title=article_in.title,
        summary=article_in.summary,
        content=content,
        cover=cover,
        category_id=article_in.category_id,
        author_id=current_user.id,
        is_published=article_in.is_published,
        is_top=article_in.is_top,
        is_recommend=article_in.is_recommend,
        is_protected=article_in.is_protected,
        protection_question=article_in.protection_question,
        protection_answer=article_in.protection_answer
    )
    
    # Add tags
    if article_in.tag_ids:
        tags = db.query(Tag).filter(Tag.id.in_(article_in.tag_ids)).all()
        article.tags = tags
        
    db.add(article)
    db.commit()
    db.refresh(article)
    
    return ResponseModel(code=200, msg="创建成功", data={"id": article.id})


@router.put("/{article_id}", response_model=ResponseModel)
def update_article(
    article_id: int,
    article_in: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings)
):
    """更新文章 (管理员)"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return ResponseModel(code=404, msg="文章不存在")
        
    if article_in.title is not None:
        article.title = article_in.title
    if article_in.summary is not None:
        article.summary = article_in.summary
    if article_in.content is not None:
        # 剥离签名
        content = article_in.content
        if settings.is_qiniu_timestamp_enabled:
            content = strip_qiniu_params(content, settings.QINIU_DOMAIN)
        article.content = content
    if article_in.cover is not None:
        # 剥离签名
        cover = article_in.cover
        if settings.is_qiniu_timestamp_enabled and cover:
            cover = strip_qiniu_params(cover, settings.QINIU_DOMAIN)
        article.cover = cover
    if article_in.category_id is not None:
        article.category_id = article_in.category_id
    if article_in.is_published is not None:
        article.is_published = article_in.is_published
    if article_in.is_top is not None:
        article.is_top = article_in.is_top
    if article_in.is_recommend is not None:
        article.is_recommend = article_in.is_recommend
        
    if article_in.is_protected is not None:
        article.is_protected = article_in.is_protected
    if article_in.protection_question is not None:
        article.protection_question = article_in.protection_question
    if article_in.protection_answer is not None:
        article.protection_answer = article_in.protection_answer
        
    # Update tags
    if article_in.tag_ids is not None:
        tags = db.query(Tag).filter(Tag.id.in_(article_in.tag_ids)).all()
        article.tags = tags
        
    db.commit()
    
    # Invalidate cache
    redis_client.delete(f"article:{article_id}")
    
    return ResponseModel(code=200, msg="更新成功")


@router.delete("/{article_id}", response_model=ResponseModel)
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除文章 (管理员)"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return ResponseModel(code=404, msg="文章不存在")
        
    db.delete(article)
    db.commit()
    
    # Invalidate cache
    redis_client.delete(f"article:{article_id}")
    redis_client.delete(f"article:{article_id}:views")
    
    return ResponseModel(code=200, msg="删除成功")


@router.get("", response_model=ResponseModel[PagedData[ArticleListItem]])
def get_articles(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    categoryId: Optional[int] = None,
    tagId: Optional[int] = None,
    keyword: Optional[str] = None,
    sort: Optional[str] = "new",
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """获取文章列表"""
    query = db.query(Article).filter(Article.is_published == True)
    
    # Filter by category
    if categoryId:
        query = query.filter(Article.category_id == categoryId)
    
    # Filter by tag
    if tagId:
        query = query.join(Article.tags).filter(Tag.id == tagId)
    
    # Search by keyword
    if keyword:
        query = query.filter(
            or_(
                Article.title.contains(keyword),
                Article.summary.contains(keyword),
                Article.content.contains(keyword)
            )
        )
    
    # Sort
    if sort == "hot":
        query = query.order_by(Article.view_count.desc())
    elif sort == "recommend":
        query = query.filter(Article.is_recommend == True).order_by(Article.created_at.desc())
    else:  # default: new
        query = query.order_by(Article.created_at.desc())
    
    # Get total count
    total = query.count()
    
    # Paginate
    articles = query.offset((current - 1) * size).limit(size).all()
    
    # Format response
    records = []
    
    # 获取七牛配置
    qiniu_domain = settings.QINIU_DOMAIN
    timestamp_key = settings.QINIU_TIMESTAMP_KEY
    expire = settings.QINIU_TIMESTAMP_EXPIRE
    
    for article in articles:
        category_name = article.category.name if article.category else ""
        
        # 刷新 cover 中的签名链接
        cover = article.cover
        if settings.is_qiniu_timestamp_enabled and cover:
            cover = refresh_qiniu_params_in_content(cover, qiniu_domain, timestamp_key, expire)
            
        records.append(ArticleListItem(
            id=article.id,
            title=article.title,
            summary=article.summary,
            cover=cover,
            createTime=article.created_at.strftime("%Y-%m-%d %H:%M:%S") if article.created_at else "",
            categoryName=category_name,
            viewCount=article.view_count,
            commentCount=article.comment_count,
            likeCount=article.like_count
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


@router.get("/{article_id}", response_model=ResponseModel[ArticleDetail])
def get_article(
    article_id: int, 
    answer: Optional[str] = Query(None, description="验证答案"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
    settings: Settings = Depends(get_settings)
):
    """获取文章详情"""
    # 绕过缓存直接查数据库以处理权限逻辑
    # 实际生产中可以优化为：先查缓存获取文章基础信息和保护状态，再进行判断
    logger.info(f"Start fetching article_id: {article_id}")
    
    try:
        article = db.query(Article).filter(Article.id == article_id).first()
        if not article:
            logger.warning(f"Article {article_id} not found")
            return ResponseModel(code=404, msg="文章不存在")
            
        if not article.is_published:
            # 只有管理员能看未发布的文章
            if not (current_user and current_user.is_admin):
                logger.warning(f"Article {article_id} not published and user is not admin")
                return ResponseModel(code=404, msg="文章不存在")
            
        # 增加阅读数 (简单实现，直接写库或 Redis)
        # 这里为了简便，沿用之前的 Redis 逻辑或直接 +1
        article.view_count += 1
        db.commit()
                
        # 权限检查
        show_content = True
        logger.info(f"Checking permission for article {article_id}. is_protected: {article.is_protected}")
        if article.is_protected:
            show_content = False
            # 管理员直接看
            if current_user and current_user.is_admin:
                show_content = True
            # 验证答案
            elif answer and answer == article.protection_answer:
                show_content = True
        
        logger.info(f"Show content for article {article_id}: {show_content}")
                
        # 构建返回
        content = article.content if show_content else "文章受保护，请输入验证答案后查看。"
        
        # 刷新内容和封面中的签名链接
        cover = article.cover
        if settings.is_qiniu_timestamp_enabled:
            qiniu_domain = settings.QINIU_DOMAIN
            timestamp_key = settings.QINIU_TIMESTAMP_KEY
            expire = settings.QINIU_TIMESTAMP_EXPIRE
            
            # 仅在有权查看内容时刷新内容中的链接
            if show_content:
                content = refresh_qiniu_params_in_content(content, qiniu_domain, timestamp_key, expire)
            
            # 刷新封面链接
            if cover:
                cover = refresh_qiniu_params_in_content(cover, qiniu_domain, timestamp_key, expire)
        
        # 格式化
        category = None
        if article.category:
            category = CategoryResponse(
                id=article.category.id,
                name=article.category.name,
                description=article.category.description,
                sort_order=article.category.sort_order,
                banner_url=article.category.banner_url,
                quote=article.category.quote,
                quote_author=article.category.quote_author
            )
            
        tags = [TagResponse(id=t.id, name=t.name, color=t.color) for t in article.tags]
        
        logger.info(f"Building response for article {article_id}")
        
        return ResponseModel(
            code=200 if show_content else 403, # 403 表示需要验证，前端据此显示输入框
            msg="success" if show_content else "protected",
            data=ArticleDetail(
                id=article.id,
                title=article.title,
                summary=article.summary or "",
                cover=cover,
                content=content,
                createTime=article.created_at.strftime("%Y-%m-%d"),
                createdAt=article.created_at,
                categoryName=article.category.name if article.category else "",
                category=category,
                tags=tags,
                viewCount=article.view_count,
                commentCount=article.comment_count,
                likeCount=article.like_count,
                is_top=article.is_top,
                is_recommend=article.is_recommend,
                is_protected=bool(article.is_protected or False),
                protection_question=article.protection_question if article.is_protected else None
            )
        )
    except Exception as e:
        logger.error(f"Error fetching article {article_id}: {str(e)}", exc_info=True)
        raise e


@router.post("/{article_id}/like", response_model=ResponseModel)
def like_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """点赞文章（防止重复点赞）"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return ResponseModel(code=404, msg="文章不存在")
    
    # 获取客户端 IP
    client_ip = request.client.host if request.client else None
    
    # 检查是否已点赞
    like_query = db.query(ArticleLike).filter(ArticleLike.article_id == article_id)
    
    if current_user:
        # 已登录用户：按用户 ID 检查
        existing_like = like_query.filter(ArticleLike.user_id == current_user.id).first()
    else:
        # 未登录用户：按 IP 检查
        if not client_ip:
            return ResponseModel(code=400, msg="无法获取客户端信息")
        existing_like = like_query.filter(
            ArticleLike.user_id == None,
            ArticleLike.ip_address == client_ip
        ).first()
    
    if existing_like:
        return ResponseModel(code=400, msg="您已经点过赞了")
    
    # 创建点赞记录
    new_like = ArticleLike(
        article_id=article_id,
        user_id=current_user.id if current_user else None,
        ip_address=client_ip
    )
    db.add(new_like)
    
    # 更新文章点赞数
    article.like_count += 1
    db.commit()
    
    return ResponseModel(code=200, msg="点赞成功", data={"likeCount": article.like_count})


@router.delete("/{article_id}/like", response_model=ResponseModel)
def unlike_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """取消点赞"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return ResponseModel(code=404, msg="文章不存在")
    
    client_ip = request.client.host if request.client else None
    
    # 查找点赞记录
    like_query = db.query(ArticleLike).filter(ArticleLike.article_id == article_id)
    
    if current_user:
        existing_like = like_query.filter(ArticleLike.user_id == current_user.id).first()
    else:
        if not client_ip:
            return ResponseModel(code=400, msg="无法获取客户端信息")
        existing_like = like_query.filter(
            ArticleLike.user_id == None,
            ArticleLike.ip_address == client_ip
        ).first()
    
    if not existing_like:
        return ResponseModel(code=400, msg="您还没有点赞")
    
    # 删除点赞记录
    db.delete(existing_like)
    
    # 更新文章点赞数
    if article.like_count > 0:
        article.like_count -= 1
    db.commit()
    
    return ResponseModel(code=200, msg="取消点赞成功", data={"likeCount": article.like_count})


@router.get("/{article_id}/like/status", response_model=ResponseModel)
def get_like_status(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """获取当前用户的点赞状态"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return ResponseModel(code=404, msg="文章不存在")
    
    client_ip = request.client.host if request.client else None
    
    like_query = db.query(ArticleLike).filter(ArticleLike.article_id == article_id)
    
    if current_user:
        existing_like = like_query.filter(ArticleLike.user_id == current_user.id).first()
    else:
        if client_ip:
            existing_like = like_query.filter(
                ArticleLike.user_id == None,
                ArticleLike.ip_address == client_ip
            ).first()
        else:
            existing_like = None
    
    return ResponseModel(code=200, data={
        "isLiked": existing_like is not None,
        "likeCount": article.like_count
    })


@router.get("/home/categorized", response_model=ResponseModel[List[CategoryWithArticles]])
def get_home_categorized_articles(db: Session = Depends(get_db)):
    """获取首页分类文章列表"""
    # Get all categories
    categories = db.query(Category).order_by(Category.sort_order).all()
    
    data = []
    for category in categories:
        # Get top 6 articles for each category
        articles = db.query(Article).filter(
            Article.category_id == category.id,
            Article.is_published == True
        ).order_by(Article.created_at.desc()).limit(6).all()
        
        if not articles:
            continue
            
        article_list = []
        for article in articles:
            article_list.append(ArticleListItem(
                id=article.id,
                title=article.title,
                summary=article.summary,
                cover=article.cover,
                createTime=article.created_at.strftime("%Y-%m-%d %H:%M:%S") if article.created_at else "",
                categoryName=category.name,
                viewCount=article.view_count,
                commentCount=article.comment_count,
                likeCount=article.like_count
            ))
            
        data.append(CategoryWithArticles(
            id=category.id,
            name=category.name,
            description=category.description,
            articles=article_list
        ))
        
    return ResponseModel(code=200, data=data)
