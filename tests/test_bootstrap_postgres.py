import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, text

from scripts.db.bootstrap_postgres import bootstrap_database, current_revision


def _metadata() -> MetaData:
    metadata = MetaData()
    Table(
        "entries",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String(100), nullable=False),
    )
    return metadata


def _stamp(db_engine, revision: str = "test_head") -> None:
    with db_engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )


def test_bootstrap_database_creates_and_versions_empty_database() -> None:
    db_engine = create_engine("sqlite:///:memory:")

    initialized = bootstrap_database(db_engine, _metadata(), lambda: _stamp(db_engine))

    assert initialized is True
    assert current_revision(db_engine) == "test_head"


def test_bootstrap_database_skips_versioned_database() -> None:
    db_engine = create_engine("sqlite:///:memory:")
    metadata = _metadata()
    metadata.create_all(db_engine)
    _stamp(db_engine, "existing_revision")

    initialized = bootstrap_database(
        db_engine,
        metadata,
        lambda: pytest.fail("stamp callback must not run for a versioned database"),
    )

    assert initialized is False
    assert current_revision(db_engine) == "existing_revision"


def test_bootstrap_database_rejects_partial_unversioned_schema() -> None:
    db_engine = create_engine("sqlite:///:memory:")
    partial = MetaData()
    Table("unexpected", partial, Column("id", Integer, primary_key=True))
    partial.create_all(db_engine)

    with pytest.raises(RuntimeError, match="refusing to stamp"):
        bootstrap_database(db_engine, _metadata(), lambda: _stamp(db_engine))
