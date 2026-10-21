"""Build Dify knowledge graph and knowledge-base import files from Jiavu parameter-model rows.

The script is read-only. It selects only the parameterized model tables and intentionally avoids account/system tables.
Database credentials must be supplied through JY_DB_USER and JY_DB_PASSWORD so secrets are not stored in this repo.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, NotRequired, TypedDict

import pymysql
from pymysql.cursors import DictCursor


DEFAULT_HOST = "192.168.2.67"
DEFAULT_PORT = 3306
DEFAULT_DATABASE = "jiavusystemdata"
DEFAULT_OUTPUT_DIR = Path(__file__).with_name("jiavu_parameter_model_export")
ROOT_NODE_ID = "selection-root:jiavu-parameter-model"
MAX_TEMPLATE_NODES = 1000
MAX_TEMPLATE_RELATIONSHIPS = 2000

DYNAMIC_FIELD_PATTERN = re.compile(r"^f_(\d+)$")
SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


class GraphNode(TypedDict):
    id: str
    name: str
    type: str
    description: str
    labels: list[str]
    properties: dict[str, Any]


class GraphRelationship(TypedDict):
    id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float
    properties: dict[str, Any]


class KnowledgeDocument(TypedDict):
    id: str
    title: str
    content: str
    metadata: dict[str, Any]


class RowBundle(TypedDict):
    catalogs: list[dict[str, Any]]
    products: list[dict[str, Any]]
    parameters: list[dict[str, Any]]
    fields: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    product_data: list[dict[str, Any]]
    static_configs: list[dict[str, Any]]
    attribute_maps: list[dict[str, Any]]
    dynamic_columns: list[str]


class BuildResult(TypedDict):
    nodes: dict[str, GraphNode]
    relationships: list[GraphRelationship]
    documents: list[KnowledgeDocument]
    stats: dict[str, int]
    warnings: list[str]


class TemplatePart(TypedDict):
    index: int
    file: str
    node_count: int
    relationship_count: int


class CliArgs(TypedDict):
    host: str
    port: int
    database: str
    output_dir: Path
    product_id: NotRequired[int]
    include_value_nodes: bool
    max_nodes_per_part: int
    max_relationships_per_part: int


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _clean_scalar(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _clean_value(item) for key, item in value.items() if item is not None and item != ""}
    if isinstance(value, list):
        return [_clean_value(item) for item in value if item is not None and item != ""]
    return _clean_scalar(value)


def _compact_properties(properties: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in properties.items():
        cleaned = _clean_value(value)
        if cleaned is None or cleaned == "" or cleaned == [] or cleaned == {}:
            continue
        compacted[key] = cleaned
    return compacted


def _short_text(value: Any, max_length: int = 120, fallback: str = "Unnamed") -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    return text[:max_length]


def _graph_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{_short_text(value, max_length=100, fallback='unknown')}"


def _node(
    node_id: str,
    name: Any,
    node_type: str,
    labels: list[str],
    properties: dict[str, Any],
    description: str = "",
) -> GraphNode:
    return {
        "id": node_id,
        "name": _short_text(name),
        "type": node_type,
        "description": _short_text(description, max_length=400, fallback=""),
        "labels": labels,
        "properties": _compact_properties(properties),
    }


def _join_name_parts(*parts: Any, max_length: int = 120) -> str:
    text_parts = [str(part).strip() for part in parts if part is not None and str(part).strip()]
    return _short_text(" - ".join(text_parts), max_length=max_length)


def _catalog_path(row: dict[str, Any]) -> str:
    return _short_text(row.get("source") or row.get("name"), max_length=120)


def _normalize_model_name(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in (".jyasm", ".jypar"):
        if text.lower().endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def _relationship(
    rel_id: str,
    source_id: str,
    target_id: str,
    relation_type: str,
    properties: dict[str, Any],
    confidence: float = 1.0,
) -> GraphRelationship:
    return {
        "id": _short_text(rel_id, max_length=160, fallback="relationship"),
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "confidence": confidence,
        "properties": _compact_properties(properties),
    }


def _quote_identifier(identifier: str) -> str:
    if not SAFE_IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(f"unsafe SQL identifier: {identifier}")
    return f"`{identifier}`"


def _select_columns(table: str, columns: list[str], where_clause: str = "") -> str:
    quoted_table = _quote_identifier(table)
    quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
    return f"SELECT {quoted_columns} FROM {quoted_table} {where_clause}".strip()


def _fetch_rows(
    cursor: DictCursor,
    table: str,
    columns: list[str],
    where_clause: str = "",
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    cursor.execute(_select_columns(table, columns, where_clause), params)
    return list(cursor.fetchall())


def _fetch_product_data_columns(cursor: DictCursor, database: str) -> list[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME AS column_name
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'productdata'
        ORDER BY ORDINAL_POSITION
        """,
        (database,),
    )
    available_columns = [str(row["column_name"]) for row in cursor.fetchall()]
    base_columns = [
        "id",
        "productId",
        "libtype",
        "catalogId",
        "name",
        "config",
        "material",
        "stock",
        "drivesinfo",
        "createDate",
    ]
    dynamic_columns = sorted(
        (column for column in available_columns if DYNAMIC_FIELD_PATTERN.match(column)),
        key=lambda column: int(DYNAMIC_FIELD_PATTERN.match(column).group(1)),  # type: ignore[union-attr]
    )
    return [column for column in base_columns if column in available_columns] + dynamic_columns


def _fetch_all_rows(args: CliArgs) -> RowBundle:
    connection = pymysql.connect(
        host=args["host"],
        port=args["port"],
        user=_require_env("JY_DB_USER"),
        password=_require_env("JY_DB_PASSWORD"),
        database=args["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        read_timeout=60,
        write_timeout=30,
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            product_where = ""
            product_params: tuple[Any, ...] = ()
            if "product_id" in args:
                product_where = "WHERE `id` = %s"
                product_params = (args["product_id"],)

            catalogs = _fetch_rows(
                cursor,
                "catalog",
                ["id", "pid", "name", "source", "treeNode", "type", "visible", "sort"],
            )
            products = _fetch_rows(
                cursor,
                "product",
                ["id", "cid", "name", "url", "treeNode", "type", "visible", "sort"],
                product_where,
                product_params,
            )
            if "product_id" in args and not products:
                raise RuntimeError(f"product id {args['product_id']} was not found")

            product_ids = [product["id"] for product in products]
            indexes_where = ""
            indexes_params: tuple[Any, ...] = ()
            product_data_where = ""
            product_data_params: tuple[Any, ...] = ()
            if product_ids:
                placeholders = ", ".join(["%s"] * len(product_ids))
                indexes_where = f"WHERE `productId` IN ({placeholders})"
                indexes_params = tuple(product_ids)
                product_data_where = f"WHERE `productId` IN ({placeholders})"
                product_data_params = tuple(product_ids)

            indexes = _fetch_rows(
                cursor,
                "productindex",
                ["indexId", "productId", "paramId", "fieldId", "sort"],
                indexes_where,
                indexes_params,
            )
            referenced_param_ids = {row["paramId"] for row in indexes}
            referenced_field_ids = {row["fieldId"] for row in indexes}

            parameters = _fetch_rows(cursor, "productparam", ["paramId", "paramName"])
            fields = _fetch_rows(cursor, "productfield", ["fieldId", "innerName", "type"])
            if "product_id" in args:
                parameters = [row for row in parameters if row["paramId"] in referenced_param_ids]
                fields = [row for row in fields if row["fieldId"] in referenced_field_ids]

            product_data_columns = _fetch_product_data_columns(cursor, args["database"])
            product_data = _fetch_rows(
                cursor,
                "productdata",
                product_data_columns,
                product_data_where,
                product_data_params,
            )
            static_configs: list[dict[str, Any]] = []
            if "product_id" not in args:
                static_configs = _fetch_rows(
                    cursor,
                    "productdatastatic",
                    ["itemID", "cfgtype", "name", "config", "catalogName", "createDate", "catalogID"],
                )
            attribute_maps = _fetch_rows(
                cursor,
                "attributmap",
                ["id", "attrName", "mapName", "createDate"],
            )
    finally:
        connection.close()

    dynamic_columns = [column for column in product_data_columns if DYNAMIC_FIELD_PATTERN.match(column)]
    return {
        "catalogs": catalogs,
        "products": products,
        "parameters": parameters,
        "fields": fields,
        "indexes": indexes,
        "product_data": product_data,
        "static_configs": static_configs,
        "attribute_maps": attribute_maps,
        "dynamic_columns": dynamic_columns,
    }


def _dynamic_values(row: dict[str, Any], dynamic_columns: list[str], field_by_id: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for column in dynamic_columns:
        value = row.get(column)
        if value is None or value == "":
            continue
        match = DYNAMIC_FIELD_PATTERN.match(column)
        field_id = int(match.group(1)) if match else None
        field = field_by_id.get(field_id or "")
        values.append(
            _compact_properties(
                {
                    "column": column,
                    "field_id": field_id,
                    "field_name": field.get("innerName") if field else column,
                    "value": value,
                }
            )
        )
    return values


def _parameter_bindings(
    product_id: Any,
    indexes_by_product: dict[Any, list[dict[str, Any]]],
    parameter_by_id: dict[Any, dict[str, Any]],
    field_by_id: dict[Any, dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    for row in sorted(indexes_by_product.get(product_id, []), key=lambda item: (item.get("sort") or 0, item["indexId"])):
        parameter = parameter_by_id.get(row["paramId"])
        field = field_by_id.get(row["fieldId"])
        if not parameter:
            warnings.append(f"productindex {row['indexId']} references missing parameter {row['paramId']}")
            continue
        if not field:
            warnings.append(f"productindex {row['indexId']} references missing field {row['fieldId']}")
            continue

        bindings.append(
            _compact_properties(
                {
                    "source_table": "productindex",
                    "source_id": row["indexId"],
                    "index_id": row["indexId"],
                    "param_id": row["paramId"],
                    "param_name": parameter.get("paramName"),
                    "field_id": row["fieldId"],
                    "field_name": field.get("innerName"),
                    "field_type": field.get("type"),
                    "dynamic_column": f"f_{row['fieldId']}",
                    "sort": row.get("sort"),
                }
            )
        )
    return bindings


def _product_data_summary(row: dict[str, Any], dynamic_columns: list[str], field_by_id: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    dynamic_values = _dynamic_values(row, dynamic_columns, field_by_id)
    return _compact_properties(
        {
            "source_table": "productdata",
            "source_id": row["id"],
            "catalog_id": row.get("catalogId"),
            "libtype": row.get("libtype"),
            "name": row.get("name"),
            "config": row.get("config"),
            "material": row.get("material"),
            "stock": row.get("stock"),
            "drivesinfo": row.get("drivesinfo"),
            "create_date": row.get("createDate"),
            "dynamic_values": dynamic_values,
            "dynamic_value_count": len(dynamic_values),
        }
    )


def _static_config_summary(row: dict[str, Any]) -> dict[str, Any]:
    return _compact_properties(
        {
            "source_table": "productdatastatic",
            "source_id": row["itemID"],
            "cfgtype": row.get("cfgtype"),
            "name": row.get("name"),
            "config": row.get("config"),
            "catalog_id": row.get("catalogID"),
            "catalog_name": row.get("catalogName"),
            "create_date": row.get("createDate"),
        }
    )


def _add_relationship(
    relationships_by_id: dict[str, GraphRelationship],
    relationship: GraphRelationship,
    nodes: dict[str, GraphNode],
    warnings: list[str],
) -> None:
    if relationship["source_id"] not in nodes or relationship["target_id"] not in nodes:
        warnings.append(
            "skipped relationship with missing endpoint: "
            f"{relationship['source_id']} -[{relationship['relation_type']}]-> {relationship['target_id']}"
        )
        return
    relationships_by_id[relationship["id"]] = relationship


def _build_graph(rows: RowBundle, include_value_nodes: bool, source_database: str = DEFAULT_DATABASE) -> BuildResult:
    nodes: dict[str, GraphNode] = {}
    relationships_by_id: dict[str, GraphRelationship] = {}
    warnings: list[str] = []

    catalog_by_id = {str(row["id"]): row for row in rows["catalogs"]}
    product_by_id = {row["id"]: row for row in rows["products"]}
    parameter_by_id = {row["paramId"]: row for row in rows["parameters"]}
    field_by_id = {row["fieldId"]: row for row in rows["fields"]}
    indexes_by_product: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    data_by_product: dict[Any, list[dict[str, Any]]] = defaultdict(list)

    for row in rows["indexes"]:
        indexes_by_product[row["productId"]].append(row)
    for row in rows["product_data"]:
        data_by_product[row["productId"]].append(row)

    static_configs_by_product: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    static_configs_by_catalog: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows["static_configs"]:
        catalog_id = row.get("catalogID")
        config_name = _normalize_model_name(row.get("name"))
        matched_product = next(
            (
                product
                for product in rows["products"]
                if _normalize_model_name(product.get("name")) == config_name
            ),
            None,
        )
        if matched_product:
            static_configs_by_product[matched_product["id"]].append(row)
        elif catalog_id:
            static_configs_by_catalog[str(catalog_id)].append(row)

    nodes[ROOT_NODE_ID] = _node(
        node_id=ROOT_NODE_ID,
        name="佳鱼参数化设计选型",
        node_type="SelectionRoot",
        labels=["SelectionRoot"],
        properties={
            "source_database": source_database,
            "domain": "parameterized_design_selection",
        },
        description="Root of Jiavu parameterized design selection tree",
    )

    for row in rows["catalogs"]:
        node_id = _graph_id("catalog", row["id"])
        static_config_summaries = [_static_config_summary(config) for config in static_configs_by_catalog.get(str(row["id"]), [])]
        nodes[node_id] = _node(
            node_id=node_id,
            name=_catalog_path(row),
            node_type="Catalog",
            labels=["Catalog"],
            properties={
                "source_table": "catalog",
                "source_id": row["id"],
                "parent_id": row.get("pid"),
                "display_name": row.get("name"),
                "source": row.get("source"),
                "tree_node": row.get("treeNode"),
                "catalog_type": row.get("type"),
                "visible": row.get("visible"),
                "sort": row.get("sort"),
                "static_configs": static_config_summaries,
                "static_config_count": len(static_config_summaries),
            },
            description="Parameter model catalog",
        )

    for row in rows["products"]:
        node_id = _graph_id("product", row["id"])
        catalog = catalog_by_id.get(str(row.get("cid")))
        parameter_bindings = _parameter_bindings(
            product_id=row["id"],
            indexes_by_product=indexes_by_product,
            parameter_by_id=parameter_by_id,
            field_by_id=field_by_id,
            warnings=warnings,
        )
        product_data_summaries = [
            _product_data_summary(data_row, rows["dynamic_columns"], field_by_id)
            for data_row in data_by_product.get(row["id"], [])
        ]
        static_config_summaries = [_static_config_summary(config) for config in static_configs_by_product.get(row["id"], [])]
        nodes[node_id] = _node(
            node_id=node_id,
            name=row["name"],
            node_type="ProductModel",
            labels=["ProductModel"],
            properties={
                "source_table": "product",
                "source_id": row["id"],
                "catalog_id": row.get("cid"),
                "catalog_name": _catalog_path(catalog) if catalog else None,
                "url": row.get("url"),
                "tree_node": row.get("treeNode"),
                "product_type": row.get("type"),
                "visible": row.get("visible"),
                "sort": row.get("sort"),
                "parameters": parameter_bindings,
                "parameter_count": len(parameter_bindings),
                "product_data": product_data_summaries,
                "product_data_count": len(product_data_summaries),
                "static_configs": static_config_summaries,
                "static_config_count": len(static_config_summaries),
            },
            description="Parameterized product model",
        )

    for row in rows["catalogs"]:
        parent_id = row.get("pid")
        if not parent_id or str(parent_id) == str(row["id"]) or str(parent_id) not in catalog_by_id:
            _add_relationship(
                relationships_by_id,
                _relationship(
                    rel_id=f"selection-root:catalog:{row['id']}",
                    source_id=ROOT_NODE_ID,
                    target_id=_graph_id("catalog", row["id"]),
                    relation_type="HAS_SELECTION_CATEGORY",
                    properties={"source_table": "catalog", "source_id": row["id"], "sort": row.get("sort")},
                ),
                nodes,
                warnings,
            )
            continue
        _add_relationship(
            relationships_by_id,
            _relationship(
                rel_id=f"catalog:{row['id']}:parent:{parent_id}",
                source_id=_graph_id("catalog", parent_id),
                target_id=_graph_id("catalog", row["id"]),
                relation_type="HAS_CHILD_CATEGORY",
                properties={"source_table": "catalog", "source_id": row["id"]},
            ),
            nodes,
            warnings,
        )

    for row in rows["products"]:
        catalog_id = row.get("cid")
        if catalog_id:
            _add_relationship(
                relationships_by_id,
                _relationship(
                    rel_id=f"product:{row['id']}:catalog:{catalog_id}",
                    source_id=_graph_id("catalog", catalog_id),
                    target_id=_graph_id("product", row["id"]),
                    relation_type="HAS_PRODUCT_MODEL",
                    properties={"source_table": "product", "source_id": row["id"], "catalog_id": catalog_id},
                ),
                nodes,
                warnings,
            )

    documents = _build_documents(
        rows=rows,
        source_database=source_database,
        catalog_by_id=catalog_by_id,
        product_by_id=product_by_id,
        parameter_by_id=parameter_by_id,
        field_by_id=field_by_id,
        indexes_by_product=indexes_by_product,
        data_by_product=data_by_product,
    )
    stats = {
        "catalog_rows": len(rows["catalogs"]),
        "product_rows": len(rows["products"]),
        "parameter_rows": len(rows["parameters"]),
        "field_rows": len(rows["fields"]),
        "productindex_rows": len(rows["indexes"]),
        "productdata_rows": len(rows["product_data"]),
        "productdatastatic_rows": len(rows["static_configs"]),
        "attributmap_rows": len(rows["attribute_maps"]),
        "graph_nodes": len(nodes),
        "graph_relationships": len(relationships_by_id),
        "knowledge_documents": len(documents),
    }
    return {
        "nodes": nodes,
        "relationships": list(relationships_by_id.values()),
        "documents": documents,
        "stats": stats,
        "warnings": warnings,
    }


def _line(label: str, value: Any) -> str | None:
    if value is None or value == "":
        return None
    return f"{label}: {value}"


def _format_dynamic_values(dynamic_values: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for value_row in dynamic_values:
        field_name = value_row.get("field_name") or value_row.get("column")
        lines.append(f"- {field_name}: {value_row.get('value')}")
    return lines


def _build_documents(
    rows: RowBundle,
    source_database: str,
    catalog_by_id: dict[str, dict[str, Any]],
    product_by_id: dict[Any, dict[str, Any]],
    parameter_by_id: dict[Any, dict[str, Any]],
    field_by_id: dict[Any, dict[str, Any]],
    indexes_by_product: dict[Any, list[dict[str, Any]]],
    data_by_product: dict[Any, list[dict[str, Any]]],
) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for product in rows["products"]:
        product_id = product["id"]
        catalog = catalog_by_id.get(str(product.get("cid")))
        lines = [
            f"参数化模型: {product.get('name') or product_id}",
            f"来源: jiavusystemdata.product#{product_id}",
        ]
        for item in [
            _line("目录", catalog.get("name") if catalog else product.get("cid")),
            _line("产品类型", product.get("type")),
            _line("可见", product.get("visible")),
            _line("排序", product.get("sort")),
        ]:
            if item:
                lines.append(item)

        lines.append("")
        lines.append("参数绑定:")
        for index_row in sorted(indexes_by_product.get(product_id, []), key=lambda item: (item.get("sort") or 0, item["indexId"])):
            parameter = parameter_by_id.get(index_row["paramId"])
            field = field_by_id.get(index_row["fieldId"])
            parameter_name = parameter.get("paramName") if parameter else index_row["paramId"]
            field_name = field.get("innerName") if field else index_row["fieldId"]
            lines.append(
                "- "
                f"sort={index_row.get('sort')}, "
                f"indexId={index_row['indexId']}, "
                f"parameter={parameter_name}(paramId={index_row['paramId']}), "
                f"field={field_name}(fieldId={index_row['fieldId']})"
            )

        product_data_rows = data_by_product.get(product_id, [])
        if product_data_rows:
            lines.append("")
            lines.append("产品数据记录:")
            for data_row in product_data_rows:
                lines.append(
                    "- "
                    f"id={data_row['id']}, "
                    f"name={data_row.get('name') or ''}, "
                    f"config={data_row.get('config') or ''}, "
                    f"material={data_row.get('material') or ''}, "
                    f"stock={data_row.get('stock') or ''}"
                )

        documents.append(
            {
                "id": f"product-model:{product_id}",
                "title": f"参数化模型 - {product.get('name') or product_id}",
                "content": "\n".join(lines),
                "metadata": _compact_properties(
                    {
                        "source_database": source_database,
                        "source_table": "product",
                        "source_id": product_id,
                        "document_type": "parameter_model",
                        "catalog_id": product.get("cid"),
                "catalog_name": _catalog_path(catalog) if catalog else None,
                    }
                ),
            }
        )

    for data_row in rows["product_data"]:
        product = product_by_id.get(data_row.get("productId"))
        dynamic_values = _dynamic_values(data_row, rows["dynamic_columns"], field_by_id)
        lines = [
            f"产品数据记录: {data_row.get('name') or data_row['id']}",
            f"来源: jiavusystemdata.productdata#{data_row['id']}",
        ]
        for item in [
            _line("所属参数化模型", product.get("name") if product else data_row.get("productId")),
            _line("配置", data_row.get("config")),
            _line("材料", data_row.get("material")),
            _line("库存", data_row.get("stock")),
            _line("驱动信息", data_row.get("drivesinfo")),
        ]:
            if item:
                lines.append(item)
        if dynamic_values:
            lines.append("")
            lines.append("动态字段值:")
            lines.extend(_format_dynamic_values(dynamic_values))

        documents.append(
            {
                "id": f"product-data:{data_row['id']}",
                "title": f"产品数据 - {data_row.get('name') or data_row['id']}",
                "content": "\n".join(lines),
                "metadata": _compact_properties(
                    {
                        "source_database": source_database,
                        "source_table": "productdata",
                        "source_id": data_row["id"],
                        "document_type": "product_data",
                        "product_id": data_row.get("productId"),
                        "product_name": product.get("name") if product else None,
                    }
                ),
            }
        )

    for config in rows["static_configs"]:
        lines = [
            f"静态配置: {config.get('name') or config['itemID']}",
            f"来源: jiavusystemdata.productdatastatic#{config['itemID']}",
        ]
        for item in [
            _line("配置类型", config.get("cfgtype")),
            _line("配置", config.get("config")),
            _line("目录", config.get("catalogName")),
            _line("创建时间", _clean_scalar(config.get("createDate"))),
        ]:
            if item:
                lines.append(item)
        documents.append(
            {
                "id": f"static-config:{config['itemID']}",
                "title": f"静态配置 - {config.get('name') or config['itemID']}",
                "content": "\n".join(lines),
                "metadata": _compact_properties(
                    {
                        "source_database": source_database,
                        "source_table": "productdatastatic",
                        "source_id": config["itemID"],
                        "document_type": "static_config",
                        "catalog_id": config.get("catalogID"),
                        "catalog_name": config.get("catalogName"),
                    }
                ),
            }
        )

    return documents


def _json_default(value: Any) -> str:
    return str(_clean_scalar(value))


def _sort_nodes(nodes: dict[str, GraphNode], node_ids: set[str] | None = None) -> list[GraphNode]:
    selected_ids = node_ids if node_ids is not None else set(nodes)
    return sorted((nodes[node_id] for node_id in selected_ids), key=lambda node: (node["type"], node["id"]))


def _write_template_part(output_dir: Path, index: int, nodes: list[GraphNode], relationships: list[GraphRelationship]) -> TemplatePart:
    filename = f"jiavu_kg_template_part_{index:03d}.json"
    path = output_dir / filename
    path.write_text(
        json.dumps(
            {"nodes": nodes, "relationships": relationships},
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    return {
        "index": index,
        "file": filename,
        "node_count": len(nodes),
        "relationship_count": len(relationships),
    }


def _write_outputs(
    output_dir: Path,
    nodes: dict[str, GraphNode],
    relationships: list[GraphRelationship],
    documents: list[KnowledgeDocument],
    stats: dict[str, int],
    warnings: list[str],
    args: CliArgs,
) -> list[TemplatePart]:
    output_dir.mkdir(parents=True, exist_ok=True)
    max_nodes = min(max(1, args["max_nodes_per_part"]), MAX_TEMPLATE_NODES)
    max_relationships = min(max(1, args["max_relationships_per_part"]), MAX_TEMPLATE_RELATIONSHIPS)

    parts: list[TemplatePart] = []
    current_relationships: list[GraphRelationship] = []
    current_node_ids: set[str] = set()
    referenced_node_ids: set[str] = set()

    def flush_relationship_part() -> None:
        nonlocal current_relationships, current_node_ids
        if not current_relationships:
            return
        parts.append(
            _write_template_part(
                output_dir=output_dir,
                index=len(parts) + 1,
                nodes=_sort_nodes(nodes, current_node_ids),
                relationships=current_relationships,
            )
        )
        current_relationships = []
        current_node_ids = set()

    for relationship in relationships:
        endpoint_ids = {relationship["source_id"], relationship["target_id"]}
        if len(endpoint_ids) > max_nodes:
            raise RuntimeError(f"relationship {relationship['id']} cannot fit into a single import template")
        next_node_ids = current_node_ids | endpoint_ids
        if current_relationships and (
            len(current_relationships) + 1 > max_relationships or len(next_node_ids) > max_nodes
        ):
            flush_relationship_part()
            next_node_ids = endpoint_ids
        current_relationships.append(relationship)
        current_node_ids = next_node_ids
        referenced_node_ids.update(endpoint_ids)
    flush_relationship_part()

    isolated_node_ids = set(nodes) - referenced_node_ids
    sorted_isolated_node_ids = sorted(isolated_node_ids)
    for start in range(0, len(sorted_isolated_node_ids), max_nodes):
        chunk_ids = set(sorted_isolated_node_ids[start : start + max_nodes])
        parts.append(
            _write_template_part(
                output_dir=output_dir,
                index=len(parts) + 1,
                nodes=_sort_nodes(nodes, chunk_ids),
                relationships=[],
            )
        )

    if not parts:
        parts.append(
            _write_template_part(
                output_dir=output_dir,
                index=1,
                nodes=_sort_nodes(nodes),
                relationships=[],
            )
        )

    documents_path = output_dir / "jiavu_kb_documents.jsonl"
    with documents_path.open("w", encoding="utf-8") as file:
        for document in documents:
            file.write(json.dumps(document, ensure_ascii=False, default=_json_default))
            file.write("\n")

    manifest = {
        "source": {
            "host": args["host"],
            "port": args["port"],
            "database": args["database"],
            "tables": [
                "catalog",
                "product",
                "productparam",
                "productfield",
                "productindex",
                "productdata",
                "productdatastatic",
                "attributmap",
            ],
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "template_limits": {
            "max_nodes_per_part": max_nodes,
            "max_relationships_per_part": max_relationships,
        },
        "stats": stats,
        "warnings": warnings,
        "knowledge_base_file": documents_path.name,
        "knowledge_graph_parts": parts,
    }
    (output_dir / "jiavu_kg_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return parts


def _parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(
        description="Build KG import templates and KB JSONL from Jiavu parameter-model business rows."
    )
    parser.add_argument("--host", default=os.environ.get("JY_DB_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("JY_DB_PORT", DEFAULT_PORT)))
    parser.add_argument("--database", default=os.environ.get("JY_DB_NAME", DEFAULT_DATABASE))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--product-id", type=int, help="Export a single product model and its records.")
    parser.add_argument(
        "--include-value-nodes",
        action="store_true",
        help="Deprecated: productdata values are kept on ProductModel properties and knowledge-base documents.",
    )
    parser.add_argument("--max-nodes-per-part", type=int, default=950)
    parser.add_argument("--max-relationships-per-part", type=int, default=1900)
    parsed = parser.parse_args()
    args: CliArgs = {
        "host": parsed.host,
        "port": parsed.port,
        "database": parsed.database,
        "output_dir": parsed.output_dir,
        "include_value_nodes": parsed.include_value_nodes,
        "max_nodes_per_part": parsed.max_nodes_per_part,
        "max_relationships_per_part": parsed.max_relationships_per_part,
    }
    if parsed.product_id is not None:
        args["product_id"] = parsed.product_id
    return args


def main() -> int:
    args = _parse_args()
    rows = _fetch_all_rows(args)
    result = _build_graph(rows, include_value_nodes=args["include_value_nodes"], source_database=args["database"])
    parts = _write_outputs(
        output_dir=args["output_dir"],
        nodes=result["nodes"],
        relationships=result["relationships"],
        documents=result["documents"],
        stats=result["stats"],
        warnings=result["warnings"],
        args=args,
    )
    print(f"wrote {args['output_dir']}")
    print(
        "graph: "
        f"{result['stats']['graph_nodes']} nodes, "
        f"{result['stats']['graph_relationships']} relationships, "
        f"{len(parts)} template parts"
    )
    print(f"knowledge base documents: {result['stats']['knowledge_documents']}")
    if result["warnings"]:
        print(f"warnings: {len(result['warnings'])}; see jiavu_kg_manifest.json")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"parameter model export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
