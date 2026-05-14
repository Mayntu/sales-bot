"""
AbstractRepository — generic base for all SQLAlchemy async repositories.

Enforces a consistent interface: every repo must implement get_by_id().
Additional query methods are defined in concrete subclasses.
"""

from __future__ import annotations

import uuid
from typing import Generic, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class AbstractRepository(Generic[T]):
    """
    Base async repository.

    Subclass it and pass the ORM model type as the generic parameter:

        class UsersRepo(AbstractRepository[User]):
            async def get_by_id(self, id: uuid.UUID) -> User | None:
                ...
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, id: uuid.UUID) -> Optional[T]:
        raise NotImplementedError(f"{self.__class__.__name__}.get_by_id() is not implemented")
