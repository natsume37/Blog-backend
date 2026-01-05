from typing import Optional, List
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


router = APIRouter(prefix="/articles", tags=["文章"])


@router.get("/admin/list", response_model=ResponseModel[PagedData[ArticleAdminListItem]])
def get_admin_articles(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取文章列表 (管理员 - 包含草稿)"""
    query = db.query(Article)
    
    if keyword:
        query = query.filter(Article.title.contains(keyword))
        
    query = query.order_by(Article.created_at.desc())
    
    total = query.count()
    articles = query.offset((current - 1) * size).limit(size).all()
    
    records = []
    for article in articles:
        category_name = article.category.name if article.category else ""
        records.append(ArticleAdminListItem(
            id=article.id,
            title=article.title,
            summary=article.summary or "",
            cover=article.cover or "",
            createTime=article.created_at.strftime("%Y-%m-%d %H:%M:%S") if article.created_at else "",
            categoryName=category_name,
            viewCount=article.view_count,
            commentCount=article.comment_count,
            likeCount=article.like_count,
            is_published=article.is_published,
            is_top=article.is_top,
            is_recommend=article.is_recommend
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
    current_user: User = Depends(get_current_admin)
):
    """创建文章 (管理员)"""
    # Check category
    if article_in.category_id:
        category = db.query(Category).filter(Category.id == article_in.category_id).first()
        if not category:
            return ResponseModel(code=404, msg="分类不存在")
            
    article = Article(
        title=article_in.title,
        summary=article_in.summary,
        content=article_in.content,
        cover=article_in.cover,
        category_id=article_in.category_id,
        author_id=current_user.id,
        is_published=article_in.is_published,
        is_top=article_in.is_top,
        is_recommend=article_in.is_recommend
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
    current_user: User = Depends(get_current_admin)
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
        article.content = article_in.content
    if article_in.cover is not None:
        article.cover = article_in.cover
    if article_in.category_id is not None:
        article.category_id = article_in.category_id
    if article_in.is_published is not None:
        article.is_published = article_in.is_published
    if article_in.is_top is not None:
        article.is_top = article_in.is_top
    if article_in.is_recommend is not None:
        article.is_recommend = article_in.is_recommend
        
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
    db: Session = Depends(get_db)
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
    for article in articles:
        category_name = article.category.name if article.category else ""
        records.append(ArticleListItem(
            id=article.id,
            title=article.title,
            summary=article.summary,
            cover=article.cover,
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
def get_article(article_id: int, db: Session = Depends(get_db)):
    """获取文章详情"""
    # Try cache first
    cache_key = f"article:{article_id}"
    cached_data = redis_client.get(cache_key)
    
    if cached_data:
        # Increment view count in Redis
        view_count_key = f"article:{article_id}:views"
        new_views = redis_client.incr(view_count_key)
        
        # Update the cached data's view count
        cached_data['viewCount'] = new_views
        
        return ResponseModel(
            code=200,
            data=ArticleDetail(**cached_data)
        )
    
    # If not in cache, query DB
    article = db.query(Article).filter(Article.id == article_id).first()
    
    if not article:
        return ResponseModel(code=404, msg="文章不存在")
    
    # Handle view count
    # We use Redis to track real-time views
    view_count_key = f"article:{article_id}:views"
    
    # If key doesn't exist, initialize from DB
    if not redis_client.get_client().exists(view_count_key):
        redis_client.get_client().set(view_count_key, article.view_count)
    
    # Increment in Redis
    new_views = redis_client.incr(view_count_key)
    
    category_name = article.category.name if article.category else ""
    tags = [TagResponse(id=tag.id, name=tag.name, color=tag.color, created_at=tag.created_at) for tag in article.tags]
    
    detail_data = ArticleDetail(
        id=article.id,
        title=article.title,
        summary=article.summary or "",
        content=article.content,
        cover=article.cover or "",
        category_id=article.category_id,
        categoryName=category_name,
        tags=tags,
        viewCount=new_views,
        commentCount=article.comment_count,
        likeCount=article.like_count,
        is_published=article.is_published,
        is_top=article.is_top,
        is_recommend=article.is_recommend,
        createdAt=article.created_at,
        updatedAt=article.updated_at
    )
    
    # Cache the detail data (excluding view count which changes often, or include it and update it)
    # We cache the structure. When reading, we overlay the dynamic view count.
    redis_client.set(cache_key, detail_data.model_dump(), expire=300) # Cache for 5 mins
    
    return ResponseModel(
        code=200,
        data=detail_data
    )


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
