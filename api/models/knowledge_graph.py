from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, DefaultFieldsMixin
from .types import StringUUID


class KnowledgeGraph(DefaultFieldsMixin, Base):
    """
    Metadata for a standalone knowledge graph library.

    Graph content lives in Neo4j and must be written with this row's `tenant_id` and `id` as `graph_id`. The relational
    row is the console-facing resource boundary; Neo4j queries must still enforce both fields because graph content is
    shared infrastructure.
    """

    __tablename__ = "knowledge_graphs"
    __table_args__ = (
        sa.Index("knowledge_graphs_tenant_id_name_idx", "tenant_id", "name"),
        sa.Index("knowledge_graphs_tenant_id_created_at_idx", "tenant_id", "created_at"),
        sa.UniqueConstraint("tenant_id", "name", name="knowledge_graphs_tenant_id_name_unique"),
    )

    tenant_id: Mapped[str] = mapped_column(StringUUID, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    description: Mapped[str] = mapped_column(sa.String(400), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    updated_by: Mapped[str] = mapped_column(StringUUID, nullable=False)
    archived: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False, server_default=sa.text("false"))
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
