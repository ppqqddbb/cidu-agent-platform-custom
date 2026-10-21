import json
import os
import sys
from pathlib import Path

import pymysql


HOST = "192.168.2.67"
PORT = 3306
DATABASE = "jiavusystemdata"
OUTPUT_PATH = Path(__file__).with_name("jiavusystemdata_schema.json")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def main() -> int:
    user = _require_env("JY_DB_USER")
    password = _require_env("JY_DB_PASSWORD")
    connection = pymysql.connect(
        host=HOST,
        port=PORT,
        user=user,
        password=password,
        database=DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    TABLE_NAME AS table_name,
                    TABLE_COMMENT AS table_comment,
                    TABLE_ROWS AS estimated_rows
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME
                """,
                (DATABASE,),
            )
            tables = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    TABLE_NAME AS table_name,
                    COLUMN_NAME AS column_name,
                    ORDINAL_POSITION AS ordinal_position,
                    COLUMN_TYPE AS column_type,
                    IS_NULLABLE AS is_nullable,
                    COLUMN_DEFAULT AS column_default,
                    COLUMN_KEY AS column_key,
                    EXTRA AS extra,
                    COLUMN_COMMENT AS column_comment
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                (DATABASE,),
            )
            columns = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    TABLE_NAME AS table_name,
                    INDEX_NAME AS index_name,
                    NON_UNIQUE AS non_unique,
                    SEQ_IN_INDEX AS seq_in_index,
                    COLUMN_NAME AS column_name
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
                """,
                (DATABASE,),
            )
            indexes = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    TABLE_NAME AS table_name,
                    COLUMN_NAME AS column_name,
                    CONSTRAINT_NAME AS constraint_name,
                    REFERENCED_TABLE_NAME AS referenced_table_name,
                    REFERENCED_COLUMN_NAME AS referenced_column_name
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s
                  AND REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION
                """,
                (DATABASE,),
            )
            foreign_keys = cursor.fetchall()
    finally:
        connection.close()

    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "database": DATABASE,
                "tables": tables,
                "columns": columns,
                "indexes": indexes,
                "foreign_keys": foreign_keys,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"schema extraction failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
