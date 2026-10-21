"""Import generated Jiavu parameter-model documents into a local Dify dataset."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from sqlalchemy import delete, func, select, text

from app_factory import create_migrations_app
from core.rag.datasource.keyword.jieba.jieba import dumps_with_sets
from core.rag.datasource.keyword.jieba.jieba_keyword_table_handler import JiebaKeywordTableHandler
from core.rag.index_processor.constant.index_type import IndexStructureType, IndexTechniqueType
from core.rag.retrieval.retrieval_methods import RetrievalMethod
from extensions.ext_database import db
from libs.datetime_utils import naive_utc_now
from models.account import Account, Tenant, TenantAccountJoin
from models.dataset import Dataset, DatasetKeywordTable, DatasetPermissionEnum, DatasetProcessRule, Document, DocumentSegment
from models.enums import DataSourceType, DocumentCreatedFrom, IndexingStatus, ProcessRuleMode, SegmentStatus


DEFAULT_EXPORT_DIR = Path(__file__).with_name("jiavu_parameter_model_export")
DEFAULT_DOCUMENTS_PATH = DEFAULT_EXPORT_DIR / "jiavu_kb_documents.jsonl"
DEFAULT_DATASET_NAME = "Jiavu 参数化模型知识库"
DEFAULT_TENANT_NAME = "default"
DEFAULT_DESCRIPTION = "Jiavu 参数化设计选型模型记录导入知识库。"
SEGMENT_MAX_CHARS = 3800


class JiavuKbDocument(TypedDict):
    id: str
    title: str
    content: str
    metadata: NotRequired[dict[str, Any]]


class ImportSummary(TypedDict):
    dataset_id: str
    tenant_id: str
    document_count: int
    segment_count: int
    keyword_count: int
    replaced: bool


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


def _find_account(tenant_id: str) -> Account:
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
        account = db.session.get(Account, _as_str(row[0]))
        if account is not None:
            return account

    join = db.session.scalar(select(TenantAccountJoin).where(TenantAccountJoin.tenant_id == tenant_id).limit(1))
    if join is not None:
        account = db.session.get(Account, _as_str(join.account_id))
        if account is not None:
            return account

    account = db.session.scalar(select(Account).order_by(Account.created_at).limit(1))
    if account is not None:
        return account

    raise RuntimeError(f"no account found for tenant {tenant_id}")


def _load_documents(path: Path) -> list[JiavuKbDocument]:
    if not path.exists():
        raise RuntimeError(f"documents file not found: {path}")

    documents: list[JiavuKbDocument] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not payload.get("id") or not payload.get("title") or not payload.get("content"):
            raise RuntimeError(f"invalid document at line {line_number}")
        documents.append(
            {
                "id": str(payload["id"]),
                "title": str(payload["title"])[:255],
                "content": str(payload["content"]),
                "metadata": dict(payload.get("metadata") or {}),
            }
        )

    if not documents:
        raise RuntimeError(f"no documents found in {path}")
    return documents


def _get_or_create_dataset(tenant_id: str, account: Account, name: str, description: str) -> Dataset:
    dataset = db.session.scalar(
        select(Dataset).where(
            Dataset.tenant_id == tenant_id,
            Dataset.name == name,
        )
    )
    now = naive_utc_now()
    retrieval_model = {
        "search_method": RetrievalMethod.KEYWORD_SEARCH.value,
        "reranking_enable": False,
        "reranking_model": {"reranking_provider_name": "", "reranking_model_name": ""},
        "top_k": 6,
        "score_threshold_enabled": False,
    }
    if dataset is not None:
        dataset.description = description
        dataset.provider = "vendor"
        dataset.permission = DatasetPermissionEnum.ALL_TEAM
        dataset.data_source_type = DataSourceType.LOCAL_FILE
        dataset.indexing_technique = IndexTechniqueType.ECONOMY
        dataset.retrieval_model = retrieval_model
        dataset.updated_by = account.id
        dataset.updated_at = now
        dataset.chunk_structure = IndexStructureType.PARAGRAPH_INDEX.value
        db.session.add(dataset)
        db.session.flush()
        return dataset

    dataset = Dataset(
        tenant_id=tenant_id,
        name=name,
        description=description,
        provider="vendor",
        permission=DatasetPermissionEnum.ALL_TEAM,
        data_source_type=DataSourceType.LOCAL_FILE,
        indexing_technique=IndexTechniqueType.ECONOMY,
        created_by=account.id,
        updated_by=account.id,
        retrieval_model=retrieval_model,
        chunk_structure=IndexStructureType.PARAGRAPH_INDEX.value,
    )
    db.session.add(dataset)
    db.session.flush()
    return dataset


def _replace_dataset_content(dataset_id: str) -> None:
    db.session.execute(delete(DocumentSegment).where(DocumentSegment.dataset_id == dataset_id))
    db.session.execute(delete(Document).where(Document.dataset_id == dataset_id))
    db.session.execute(delete(DatasetKeywordTable).where(DatasetKeywordTable.dataset_id == dataset_id))
    db.session.execute(delete(DatasetProcessRule).where(DatasetProcessRule.dataset_id == dataset_id))
    db.session.flush()


def _get_or_create_process_rule(dataset: Dataset, account: Account) -> DatasetProcessRule:
    process_rule = db.session.scalar(
        select(DatasetProcessRule)
        .where(DatasetProcessRule.dataset_id == dataset.id)
        .order_by(DatasetProcessRule.created_at.desc())
        .limit(1)
    )
    if process_rule is not None:
        return process_rule

    process_rule = DatasetProcessRule(
        dataset_id=dataset.id,
        mode=ProcessRuleMode.AUTOMATIC,
        rules=json.dumps(DatasetProcessRule.AUTOMATIC_RULES, ensure_ascii=False),
        created_by=account.id,
    )
    db.session.add(process_rule)
    db.session.flush()
    return process_rule


def _iter_segments(content: str) -> Iterable[str]:
    if len(content) <= SEGMENT_MAX_CHARS:
        yield content
        return

    current: list[str] = []
    current_length = 0
    for line in content.splitlines():
        line_length = len(line) + 1
        if current and current_length + line_length > SEGMENT_MAX_CHARS:
            yield "\n".join(current).strip()
            current = []
            current_length = 0
        current.append(line)
        current_length += line_length

    if current:
        yield "\n".join(current).strip()


def _create_documents(
    dataset: Dataset,
    process_rule: DatasetProcessRule,
    account: Account,
    source_documents: list[JiavuKbDocument],
) -> tuple[int, int, dict[str, set[str]]]:
    now = naive_utc_now()
    batch = time.strftime("%Y%m%d%H%M%S")
    keyword_handler = JiebaKeywordTableHandler()
    keyword_table: dict[str, set[str]] = {}
    document_count = 0
    segment_count = 0

    start_position = db.session.scalar(
        select(func.coalesce(func.max(Document.position), 0)).where(Document.dataset_id == dataset.id)
    )
    assert start_position is not None
    position = int(start_position) + 1

    for source_document in source_documents:
        content = source_document["content"]
        metadata = source_document.get("metadata", {})
        document = Document(
            tenant_id=dataset.tenant_id,
            dataset_id=dataset.id,
            position=position,
            data_source_type=DataSourceType.LOCAL_FILE,
            data_source_info=json.dumps(
                {
                    "source": "jiavu_parameter_model_export",
                    "source_id": source_document["id"],
                },
                ensure_ascii=False,
            ),
            dataset_process_rule_id=process_rule.id,
            batch=batch,
            name=source_document["title"],
            created_from=DocumentCreatedFrom.WEB,
            created_by=account.id,
            created_at=now,
            processing_started_at=now,
            word_count=len(content),
            parsing_completed_at=now,
            cleaning_completed_at=now,
            splitting_completed_at=now,
            tokens=len(content),
            indexing_latency=0.0,
            completed_at=now,
            indexing_status=IndexingStatus.COMPLETED,
            enabled=True,
            archived=False,
            updated_at=now,
            doc_type=None,
            doc_metadata=metadata,
            doc_form=IndexStructureType.PARAGRAPH_INDEX,
            doc_language="Chinese",
        )
        db.session.add(document)
        db.session.flush()

        for segment_position, segment_content in enumerate(_iter_segments(content), start=1):
            if not segment_content:
                continue
            segment_node_id = str(uuid4())
            keywords = keyword_handler.extract_keywords(segment_content, dataset.keyword_number or 10)
            segment = DocumentSegment(
                tenant_id=dataset.tenant_id,
                dataset_id=dataset.id,
                document_id=document.id,
                position=segment_position,
                content=segment_content,
                word_count=len(segment_content),
                tokens=len(segment_content),
                keywords=list(keywords),
                index_node_id=segment_node_id,
                index_node_hash=str(hash(segment_content)),
                status=SegmentStatus.COMPLETED,
                enabled=True,
                indexing_at=now,
                completed_at=now,
                created_by=account.id,
                created_at=now,
                updated_by=account.id,
                updated_at=now,
            )
            db.session.add(segment)
            for keyword in keywords:
                keyword_table.setdefault(keyword, set()).add(segment_node_id)
            segment_count += 1

        document_count += 1
        position += 1

    return document_count, segment_count, keyword_table


def _save_keyword_table(dataset: Dataset, keyword_table: dict[str, set[str]]) -> int:
    payload = {
        "__type__": "keyword_table",
        "__data__": {"index_id": dataset.id, "summary": None, "table": keyword_table},
    }
    dataset_keyword_table = DatasetKeywordTable(
        dataset_id=dataset.id,
        keyword_table=dumps_with_sets(payload),
        data_source_type="database",
    )
    db.session.add(dataset_keyword_table)
    return len(keyword_table)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Jiavu KB documents into the local Dify dev environment.")
    parser.add_argument("--documents-path", type=Path, default=DEFAULT_DOCUMENTS_PATH)
    parser.add_argument("--tenant-name", default=DEFAULT_TENANT_NAME)
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    parser.add_argument("--replace", action="store_true", help="Delete existing documents before importing.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_documents = _load_documents(args.documents_path)
    app = create_migrations_app()
    with app.app_context():
        tenant = _find_tenant(args.tenant_name)
        tenant_id = _as_str(tenant.id)
        account = _find_account(tenant_id)
        dataset = _get_or_create_dataset(
            tenant_id=tenant_id,
            account=account,
            name=args.dataset_name,
            description=args.description,
        )
        if args.replace:
            _replace_dataset_content(dataset.id)
        process_rule = _get_or_create_process_rule(dataset=dataset, account=account)
        document_count, segment_count, keyword_table = _create_documents(
            dataset=dataset,
            process_rule=process_rule,
            account=account,
            source_documents=source_documents,
        )
        keyword_count = _save_keyword_table(dataset=dataset, keyword_table=keyword_table)
        dataset.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.session.add(dataset)
        db.session.commit()

        summary: ImportSummary = {
            "dataset_id": dataset.id,
            "tenant_id": tenant_id,
            "document_count": document_count,
            "segment_count": segment_count,
            "keyword_count": keyword_count,
            "replaced": args.replace,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Jiavu KB import failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
