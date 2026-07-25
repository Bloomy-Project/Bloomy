import logging
from pathlib import Path
from typing import Optional
import aiosqlite

log = logging.getLogger(__name__)

__all__ = [
    "DatabaseManager",
    "DatabaseSession",
]


class DatabaseSession:
    """
    自動的にトランザクション（COMMIT / ROLLBACK）を制御する非同期コンテキストマネージャ。
    """

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn
        self._cursor: Optional[aiosqlite.Cursor] = None

    async def __aenter__(self) -> aiosqlite.Cursor:
        # トランザクションを明示的に開始
        await self._conn.execute("BEGIN TRANSACTION;")
        self._cursor = await self._conn.cursor()
        return self._cursor

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> Optional[bool]:
        if self._cursor:
            await self._cursor.close()

        if exc_type is not None:
            # セッション内で例外が発生した場合は自動でロールバックする
            log.error("Transaction failed. Rolling back...", exc_info=(exc_type, exc_val, exc_tb))
            await self._conn.rollback()
            return False  # 例外を呼び出し元に伝播させる

        # 正常終了した場合はコミットする
        await self._conn.commit()
        return True


class DatabaseManager:
    """
    データベースの接続状態とライフサイクルを管理するマネージャ。
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """データベースへの非同期接続を確立し、初期設定を行います。"""
        if self._conn is not None:
            return

        # 保存先ディレクトリが存在しない場合は作成
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = await aiosqlite.connect(self.db_path)

        # 行データにカラム名でアクセスできるようにする (row["column_name"])
        self._conn.row_factory = aiosqlite.Row

        # 外部キー制約の有効化、およびパフォーマンス向上のためのWALモード設定
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")

        log.info("Database connection established: %s", self.db_path)

    async def close(self) -> None:
        """データベース接続を安全に閉じます。"""
        if self._conn:
            await self._conn.close()
            self._conn = None
            log.info("Database connection closed.")

    def session(self) -> DatabaseSession:
        """
        トランザクション付きのデータベースセッションを開始します。

        Usage:
            async with app.db.session() as cursor:
                await cursor.execute(...)
        """
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() before opening a session.")
        return DatabaseSession(self._conn)