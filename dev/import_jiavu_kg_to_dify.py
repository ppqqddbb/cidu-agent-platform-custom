"""Import generated Jiavu parameter-model graph templates into a Dify dev knowledge graph."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from sqlalchemy import select, text

from app_factory import create_migrations_app
from core.knowledge_graph.entities import GraphImportTemplate
from extensions.ext_database import db
from models.account import Account, Tenant, TenantAccountJoin
from models.knowledge_graph import KnowledgeGraph
from services.knowledge_graph_service import KnowledgeGraphService


DEFAULT_EXPORT_DIR = Path(__file__).with_name("jiavu_parameter_model_export")
DEFAULT_GRAPH_NAME = "Jiavu 参数化模型"
DEFAULT_TENANT_NAME = "default"


class ImportSummary(TypedDict):
    graph_id: str
    tenant_id: str
    imported_nodes: int
    imported_relationships: int
    part_count: int
    overview_node_count: int
    overview_relationship_count: int


def _as_str(value: Any) -> str:
    return str(value)


def _find_tenant(tenant_name: str) -> Tenant:
    tenant = db.session.scalar(
        select(Tenant).where(
            Tenant.name == tenant_name,
            Tenant.status == "normal",
        )
    )
    if tenant is None:
        tenant = db.session.scalar(select(Tenant).where(Tenant.status == "normal").order_by(Tenant.created_at))
    if tenant is None:
        raise RuntimeError("no active tenant found")
    return tenant


def _find_user_id(tenant_id: str) -> str:
    row = db.session.execute(
        text(
            """
            SELECT a.id
            FROM accounts a
            JOIN tenant_account_joins taj ON taj.account_id = a.id
            WHERE taj.tenant_id = :tenant_id
            ORDER BY
              CASE WHEN taj.role IN ('owner', 'admin') THEN 0 ELSE 1 END,
              a.created_at ASC
            LIMIT 1
            """
        ),
        {"tenant_id": tenant_id},
    ).first()
    if row:
        return _as_str(row[0])

    account = db.session.scalar(select(Account).order_by(Account.created_at).limit(1))
    if account is not None:
        return _as_str(account.id)

    join = db.session.scalar(select(TenantAccountJoin).where(TenantAccountJoin.tenant_id == tenant_id).limit(1))
    if join is not None:
        return _as_str(join.account_id)

    raise RuntimeError(f"no account found for tenant {tenant_id}")


def _get_or_create_graph(tenant_id: str, user_id: str, graph_name: str) -> KnowledgeGraph:
    graph = db.session.scalar(
        select(KnowledgeGraph).where(
            KnowledgeGraph.tenant_id == tenant_id,
            KnowledgeGraph.name == graph_name,
            KnowledgeGraph.archived.is_(False),
        )
    )
    if graph is not None:
        return graph
    return KnowledgeGraphService.create_graph(
        tenant_id=tenant_id,
        user_id=user_id,
        name=graph_name,
        description="Jiavu 参数化模型业务记录导入图谱",
    )


def _import_parts(export_dir: Path, tenant_id: str, graph_id: str, user_id: str) -> tuple[int, int, int]:
    template_paths = sorted(export_dir.glob("jiavu_kg_template_part_*.json"))
    if not template_paths:
        raise RuntimeError(f"no template parts found in {export_dir}")

    service = KnowledgeGraphService()
    total_nodes = 0
    total_relationships = 0
    try:
        for path in template_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            template = GraphImportTemplate.model_validate(payload)
            result = service.import_template(
                tenant_id=tenant_id,
                graph_id=graph_id,
                template=template,
                user_id=user_id,
            )
            total_nodes += result.node_count
            total_relationships += result.relationship_count
            print(f"imported {path.name}: nodes={result.node_count}, relationships={result.relationship_count}")
    finally:
        service._retriever.close()

    return total_nodes, total_relationships, len(template_paths)


def _clear_graph_content(tenant_id: str, graph_id: str) -> None:
    service = KnowledgeGraphService()
    graph_store = service._retriever._create_graph_store()
    try:
        graph_store.structured_query(
            """
            MATCH (node:KnowledgeGraphEntity {tenant_id: $tenant_id, graph_id: $graph_id})
            DETACH DELETE node
            """,
            param_map={"tenant_id": tenant_id, "graph_id": graph_id},
        )
    finally:
        graph_store.close()
        service._retriever.close()


def _overview_counts(tenant_id: str, graph_id: str) -> tuple[int, int]:
    service = KnowledgeGraphService()
    try:
        overview = service.get_overview(tenant_id=tenant_id, graph_id=graph_id, limit=1)
        return overview.node_count, overview.relationship_count
    finally:
        service._retriever.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Jiavu KG template parts into the local Dify dev environment.")
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--tenant-name", default=DEFAULT_TENANT_NAME)
    parser.add_argument("--graph-name", default=DEFAULT_GRAPH_NAME)
    parser.add_argument("--replace", action="store_true", help="Delete existing Neo4j content for the graph before importing.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    app = create_migrations_app()
    with app.app_context():
        tenant = _find_tenant(args.tenant_name)
        tenant_id = _as_str(tenant.id)
        user_id = _find_user_id(tenant_id)
        graph = _get_or_create_graph(tenant_id=tenant_id, user_id=user_id, graph_name=args.graph_name)
        graph_id = _as_str(graph.id)
        print(f"target tenant={tenant.name} ({tenant_id})")
        print(f"target graph={graph.name} ({graph_id})")
        if args.replace:
            _clear_graph_content(tenant_id=tenant_id, graph_id=graph_id)
            print("cleared existing graph content")

        imported_nodes, imported_relationships, part_count = _import_parts(
            export_dir=args.export_dir,
            tenant_id=tenant_id,
            graph_id=graph_id,
            user_id=user_id,
        )
        overview_node_count, overview_relationship_count = _overview_counts(tenant_id=tenant_id, graph_id=graph_id)
        summary: ImportSummary = {
            "graph_id": graph_id,
            "tenant_id": tenant_id,
            "imported_nodes": imported_nodes,
            "imported_relationships": imported_relationships,
            "part_count": part_count,
            "overview_node_count": overview_node_count,
            "overview_relationship_count": overview_relationship_count,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Jiavu KG import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
