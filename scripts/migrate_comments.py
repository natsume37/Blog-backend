"""
评论表迁移脚本 - 添加 content_type 和 content_id 字段，移除 article_id

运行方式:
cd backend
python -m scripts.migrate_comments
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine, SessionLocal


def migrate():
    """执行数据库迁移"""
    db = SessionLocal()
    
    try:
        # 检查 content_type 字段是否已存在
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'comments' AND column_name = 'content_type'
        """))
        
        has_content_type = result.fetchone() is not None
        
        # 检查 article_id 字段是否还存在
        result2 = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'comments' AND column_name = 'article_id'
        """))
        
        has_article_id = result2.fetchone() is not None
        
        if has_content_type and not has_article_id:
            print("✓ 迁移已完成，无需重复执行")
            return
        
        print("开始迁移评论表...")
        
        # 如果还没有 content_type 字段，先添加
        if not has_content_type:
            db.execute(text("""
                ALTER TABLE comments 
                ADD COLUMN content_type VARCHAR(50) DEFAULT 'article' NOT NULL
            """))
            print("✓ 添加 content_type 字段")
            
            db.execute(text("""
                ALTER TABLE comments 
                ADD COLUMN content_id INTEGER DEFAULT 0 NOT NULL
            """))
            print("✓ 添加 content_id 字段")
            
            # 迁移现有数据
            db.execute(text("""
                UPDATE comments 
                SET content_id = article_id, content_type = 'article'
                WHERE article_id IS NOT NULL
            """))
            print("✓ 迁移现有数据")
        
        # 如果 article_id 还存在，删除它
        if has_article_id:
            # 查找外键约束名称
            fk_result = db.execute(text("""
                SELECT CONSTRAINT_NAME 
                FROM information_schema.KEY_COLUMN_USAGE 
                WHERE TABLE_NAME = 'comments' 
                AND COLUMN_NAME = 'article_id' 
                AND REFERENCED_TABLE_NAME IS NOT NULL
            """))
            
            fk_row = fk_result.fetchone()
            if fk_row:
                fk_name = fk_row[0]
                print(f"  找到外键约束: {fk_name}")
                
                # 先删除外键约束
                db.execute(text(f"ALTER TABLE comments DROP FOREIGN KEY {fk_name}"))
                print(f"✓ 删除外键约束 {fk_name}")
            
            # 删除 article_id 字段
            db.execute(text("ALTER TABLE comments DROP COLUMN article_id"))
            print("✓ 删除 article_id 字段")
        
        # 创建索引（如果不存在）
        try:
            db.execute(text("""
                CREATE INDEX ix_comments_content_type_id 
                ON comments(content_type, content_id)
            """))
            print("✓ 创建索引")
        except:
            print("✓ 索引已存在")
        
        db.commit()
        print("\n✅ 迁移完成!")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 迁移失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
