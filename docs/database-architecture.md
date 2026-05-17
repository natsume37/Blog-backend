# PostgreSQL 数据库架构与迁移方案

## 目标架构

生产数据库从 MySQL 切换到 PostgreSQL，本服务继续通过 SQLAlchemy ORM 访问数据库。

- 应用连接串：`postgresql+psycopg://blog_app:***@127.0.0.1:5432/blog_pg`
- 驱动：`psycopg[binary]`
- 连接池：由 `DATABASE_POOL_SIZE` 和 `DATABASE_MAX_OVERFLOW` 控制，生产默认 `20 + 10`
- 迁移版本：目标库建好 schema 后写入当前 Alembic head，后续增量仍使用 `alembic upgrade head`

## Schema 分区

当前 schema 按业务域组织：

- 内容域：`articles`、`categories`、`tags`、`article_tags`、`article_versions`
- 互动域：`comments`、`article_likes`、`comment_likes`、`messages`
- 记录域：`book_records`、`book_note_summaries`、`movie_records`、`weread_sync_state`
- 用户与安全：`users`、`login_logs`、`audit_logs`
- 站点能力：`site_info`、`resources`、`tool_items`、`friend_links`、`changelogs`
- 插件域：`plugin_installs`、`plugin_settings`、`wechat_broadcast_tasks`、`wechat_qrcode_records`
- 访问统计：`visit_logs`

主要约束沿用 ORM 定义：

- 主键使用 PostgreSQL sequence-backed integer primary key。
- 文章、标签、分类、微信读书源 ID 等唯一约束保持不变。
- 评论、点赞、书摘摘要等子表通过外键级联删除。
- 公开可见性字段继续使用字符串枚举约定：`public`、`login`、`private`。

## 迁移流程

1. 停止后端服务，避免切换期间 MySQL 继续写入。
2. 使用 `scripts/db/backup_mysql.py` 对 MySQL 做一致性备份。
3. 创建 PostgreSQL 数据库 `blog_pg` 和应用用户 `blog_app`。
4. 使用 `scripts/db/mysql_to_postgres.py --drop-target` 建 PG schema、复制数据、重置 sequence、写入 Alembic head。
5. 核对脚本输出的每张表 `source == copied == target`。
6. 把生产 `DATABASE_URL` 和 GitHub Actions secret 切到 PostgreSQL。
7. 执行 `alembic upgrade head`，重启后端，检查健康接口和核心页面。

## 备份与回退

- 备份文件为 gzip 压缩的 SQL dump，默认输出到 `backups/db`。
- 每个备份旁边会生成 manifest，记录数据库名、时间、大小和 SHA-256。
- 回退策略：保留 MySQL 不删除。若 PG 切换后出现问题，把 `DATABASE_URL` 改回 MySQL，重启服务即可回退到切换前备份点。
- 切换完成并稳定运行后，再单独安排 MySQL 下线，不在本次迁移中删除旧库。

## 后续优化

- 给 `visit_logs.created_at`、`book_records.source/status/visibility`、`articles.slug/created_at` 等高频查询字段补充或复核索引。
- 后续 Alembic 新迁移必须使用跨数据库类型，避免再引入 `sqlalchemy.dialects.mysql`。
- 对 `tags_json`、`stats_json` 等 Text 字段可在后续版本逐步迁移为 PostgreSQL JSONB。
