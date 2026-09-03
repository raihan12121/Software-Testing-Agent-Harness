"""Unit tests for DatabaseAdapter and transactional test isolation (R-EXEC-1)."""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from sentinel.adapters.db_adapter.adapter import DatabaseAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_db_adapter_discovery_and_schema(tmp_path: Path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT);")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL);")
    conn.commit()
    conn.close()

    config = TargetConfig(target_type="database", name="test-db", base_url=str(db_file))
    adapter = DatabaseAdapter(config)
    model = adapter.discover(config)

    assert model.target_type == "database"
    assert len(model.endpoints) == 2
    paths = [ep["path"] for ep in model.endpoints]
    assert "table://users" in paths
    assert "table://orders" in paths
    adapter.close()


def test_db_adapter_query_and_artifact_capture(tmp_path: Path):
    db_file = tmp_path / "query_test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO items (name) VALUES ('widget_a'), ('widget_b');")
    conn.commit()
    conn.close()

    config = TargetConfig(target_type="database", name="query-db", base_url=str(db_file))
    adapter = DatabaseAdapter(config)

    step = TestStep(action="query", path="SELECT * FROM items ORDER BY id;")
    obs = adapter.execute_action(step)

    assert obs.error is None
    assert obs.raw_result["status_code"] == 200
    assert obs.raw_result["rows_affected"] == 2
    assert len(obs.raw_result["rows"]) == 2
    assert obs.raw_result["rows"][0]["name"] == "widget_a"
    assert len(obs.artifacts) == 1
    adapter.close()


def test_db_adapter_transactional_rollback_isolation(tmp_path: Path):
    """Verify R-EXEC-1: Mutating test steps are rolled back, leaving zero persistent test data."""
    db_file = tmp_path / "rollback_test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance REAL);")
    conn.execute("INSERT INTO accounts (id, balance) VALUES (1, 100.0);")
    conn.commit()
    conn.close()

    config = TargetConfig(target_type="database", name="rollback-db", base_url=str(db_file))
    adapter = DatabaseAdapter(config)

    # 1. Mutating test step (INSERT)
    insert_step = TestStep(
        action="insert",
        body="INSERT INTO accounts (id, balance) VALUES (999, 5000.0);",
    )
    insert_obs = adapter.execute_action(insert_step)
    assert insert_obs.error is None
    assert insert_obs.raw_result["is_mutation"] is True

    # 2. Verify account 999 does NOT exist in the database (R-EXEC-1 rollback verification)
    verify_step = TestStep(
        action="select",
        body="SELECT * FROM accounts WHERE id = 999;",
    )
    verify_obs = adapter.execute_action(verify_step)
    assert verify_obs.error is None
    assert len(verify_obs.raw_result["rows"]) == 0, "Mutated row was not rolled back (R-EXEC-1 violated)!"
    adapter.close()


def test_db_adapter_postgres_rollback_isolation():
    """Verify PostgreSQL connection and SAVEPOINT rollback isolation (P2 item 12)."""
    config = TargetConfig(
        target_type="database",
        name="pg-target",
        base_url="postgresql://localhost:5432/appdb",
        allowed_hosts=["localhost", "127.0.0.1"],
    )
    adapter = DatabaseAdapter(config)

    mock_pg_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1
    mock_pg_conn.cursor.return_value.__enter__.return_value = mock_cursor
    adapter._pg_conn = mock_pg_conn

    # 1. Mutating query on Postgres
    step = TestStep(action="insert", body="INSERT INTO users (email) VALUES ('test@corp.com');")
    obs = adapter.execute_action(step)

    assert obs.error is None
    assert obs.raw_result["engine"] == "postgres"
    assert obs.raw_result["is_mutation"] is True

    # Verify SAVEPOINT and ROLLBACK TO SAVEPOINT were issued per R-EXEC-1
    savepoint_calls = [call[0][0] for call in mock_pg_conn.execute.call_args_list]
    assert any("SAVEPOINT sentinel_step_isolation" in c for c in savepoint_calls)
    assert any("ROLLBACK TO SAVEPOINT sentinel_step_isolation" in c for c in savepoint_calls)
    adapter.close()


def test_db_adapter_mongo_isolation():
    """Verify MongoDB collection actions and immediate deletion rollback (P2 item 12)."""
    config = TargetConfig(
        target_type="database",
        name="mongo-target",
        base_url="mongodb://localhost:27017/shop",
        allowed_hosts=["localhost", "127.0.0.1"],
    )
    adapter = DatabaseAdapter(config)

    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_insert_res = MagicMock()
    mock_insert_res.inserted_id = "doc_12345"
    mock_col.insert_one.return_value = mock_insert_res
    mock_db.__getitem__.return_value = mock_col
    mock_client.__getitem__.return_value = mock_db
    adapter._mongo_client = mock_client

    # 1. Insert action on Mongo with rollback: True
    step = TestStep(
        action="insert_one",
        path="collection://customers",
        body={"name": "Alice", "status": "active"},
        metadata={"rollback": True},
    )
    obs = adapter.execute_action(step)

    assert obs.error is None
    assert obs.raw_result["engine"] == "mongo"
    mock_col.insert_one.assert_called_once()
    # Verify document was deleted immediately for rollback isolation (R-EXEC-1)
    mock_col.delete_one.assert_called_with({"_id": "doc_12345"})
    adapter.close()


def test_db_adapter_allowlist_security():
    """Verify remote database host outside allowlist is blocked (R-SAFE-5)."""
    config = TargetConfig(
        target_type="database",
        name="UntrustedDB",
        base_url="postgresql://untrusted-remote-db.com:5432/secrets",
        allowed_hosts=["localhost", "127.0.0.1"],
    )
    adapter = DatabaseAdapter(config)
    obs = adapter.execute_action(TestStep(action="query", body="SELECT * FROM secrets;"))
    assert obs.error is not None
    assert "SECURITY_BLOCK" in obs.error
    assert "R-SAFE-5" in obs.error
    adapter.close()
