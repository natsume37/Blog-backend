import sys
import os
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.models.article import Article, Tag
from sqlalchemy import func

db = SessionLocal()
try:
    article_count = db.query(func.count(Article.id)).filter(Article.is_published == True).scalar()
    tag_count = db.query(func.count(Tag.id)).scalar()
    view_count = db.query(func.sum(Article.view_count)).scalar()
    
    print(f"Articles: {article_count}")
    print(f"Tags: {tag_count}")
    print(f"Views: {view_count}")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
