import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.core.database import SessionLocal
from app.core.cache import redis_client
from app.models.article import Article
from app.core.config import settings

logger = logging.getLogger(__name__)

# 创建调度器实例
scheduler = AsyncIOScheduler()

async def sync_views_to_db():
    """
    定时任务：将 Redis 中的文章浏览量同步回数据库
    """
    logger.info("Starting scheduled task: Sync views to DB")
    db = SessionLocal()
    try:
        # 获取 Redis 客户端
        r = redis_client.get_client()
        
        # 使用 scan_iter 遍历所有浏览量 key，避免阻塞
        # Key 格式: article:{id}:views
        cursor = '0'
        pattern = "article:*:views"
        
        updated_count = 0
        
        # 收集所有需要更新的数据
        updates = {}
        
        for key in r.scan_iter(match=pattern):
            try:
                # key 示例: article:12:views
                parts = key.split(":")
                if len(parts) == 3 and parts[1].isdigit():
                    article_id = int(parts[1])
                    view_count = r.get(key)
                    if view_count:
                        updates[article_id] = int(view_count)
            except Exception as e:
                logger.error(f"Error parsing key {key}: {e}")
                continue
        
        if not updates:
            logger.info("No views to sync")
            return

        # 批量更新数据库
        # 这种方式比逐条 update 更高效，但 SQLAlchemy ORM 逐条 update 比较简单
        # 为了性能，我们这里使用逐条更新，但都在一个事务中提交
        # 如果数据量巨大，可以考虑 bulk_update_mappings
        
        for article_id, count in updates.items():
            # 仅当 Redis 中的计数大于数据库中的计数时才更新（防止回退，虽然理论上 Redis 是最新的）
            # 或者直接覆盖，以 Redis 为准
            db.query(Article).filter(Article.id == article_id).update(
                {"view_count": count}
            )
            updated_count += 1
        
        db.commit()
        logger.info(f"Successfully synced {updated_count} articles views to DB")
        
    except Exception as e:
        logger.error(f"Error syncing views: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

def start_scheduler():
    """启动调度器"""
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")
        
        # 添加定时任务
        scheduler.add_job(
            sync_views_to_db,
            trigger=IntervalTrigger(minutes=settings.SYNC_VIEWS_INTERVAL_MINUTES),
            id="sync_views_job",
            replace_existing=True,
            name="Sync Article Views"
        )
        logger.info(f"Added sync_views_job with interval {settings.SYNC_VIEWS_INTERVAL_MINUTES} minutes")

def stop_scheduler():
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")
