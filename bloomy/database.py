import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base

log = logging.getLogger(__name__)

__all__ = [
    "DatabaseManager",
    "Base",
]

# モデル定義用のベースクラス
Base = declarative_base()


class DatabaseManager:
    """
    データベースの接続状態とライフサイクルを管理するマネージャ。
    """

    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_maker: async_sessionmaker[AsyncSession] | None = None

    async def connect(self, url: str) -> None:
        """データベースへの非同期接続を確立し、セッションファクトリを設定します。"""
        if self.engine is not None:
            return

        # aiosqlite をドライバとして使用する非同期エンジンを作成
        self.engine = create_async_engine(
            url,
            echo=False,  # SQLクエリのログ出力が必要な場合は True に設定
        )

        # セッションファクトリの設定
        self.session_maker = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        log.info("Database connection established: %s", self.engine.url)

    async def close(self) -> None:
        """データベースエンジンを安全に閉じます。"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_maker = None
            log.info("Database connection closed.")

    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        トランザクション付きの非同期データベースセッションを提供するコンテキストマネージャ。

        Usage:
            async with app.db.session() as session:
                result = await session.execute(select(User))
                ...
        """
        if self.session_maker is None:
            raise RuntimeError("Database is not connected. Call connect() before opening a session.")

        async with self.session_maker() as session:
            try:
                yield session
                # 例外が発生しなければ自動でコミットされる
                await session.commit()
            except Exception:
                # 例外が発生した場合は自動でロールバック
                await session.rollback()
                log.error("Transaction failed. Rolling back...", exc_info=True)
                raise
