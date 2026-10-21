import logging

from flask import request, send_file
from flask_restx import Resource
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, or_, select
from werkzeug.exceptions import Forbidden, NotFound

import services
from configs import dify_config
from controllers.common.errors import (
    FilenameNotExistsError,
    FileTooLargeError,
    NoFileUploadedError,
    TooManyFilesError,
    UnsupportedFileTypeError,
)
from controllers.console import console_ns
from controllers.console.wraps import (
    account_initialization_required,
    setup_required,
)
from extensions.ext_database import db
from fields.base import ResponseModel
from libs.login import current_account_with_tenant, login_required
from models.account import Account
from models.model import MessageFile, UploadFile
from services.file_service import FileService

logger = logging.getLogger(__name__)

DEFAULT_REF_TEMPLATE_SWAGGER_2_0 = "#/definitions/{model}"
WORKSPACE_FILE_STORAGE_NAMESPACE = "workspace_files"
LEGACY_UPLOAD_FILE_STORAGE_NAMESPACE = "upload_files"


def _workspace_file_key_prefix(tenant_id: str) -> str:
    return f"{WORKSPACE_FILE_STORAGE_NAMESPACE}/{tenant_id}/"


def _legacy_upload_file_key_prefix(tenant_id: str) -> str:
    return f"{LEGACY_UPLOAD_FILE_STORAGE_NAMESPACE}/{tenant_id}/"


def _workspace_visible_file_filter(tenant_id: str):
    message_file_exists = exists().where(MessageFile.upload_file_id == UploadFile.id)
    return or_(
        UploadFile.key.like(f"{_workspace_file_key_prefix(tenant_id)}%"),
        and_(
            UploadFile.key.like(f"{_legacy_upload_file_key_prefix(tenant_id)}%"),
            or_(
                UploadFile.file_type == "temporary",
                and_(UploadFile.file_type == "formal", ~message_file_exists),
            ),
        ),
    )


class WorkspaceFileListQuery(BaseModel):
    page: int = Field(default=1, ge=1, le=99999)
    limit: int = Field(default=20, ge=1, le=100)
    keyword: str | None = Field(default=None)
    file_type: str | None = Field(default=None)


class WorkspaceFileItem(ResponseModel):
    id: str
    name: str
    size: int
    mime_type: str | None = None
    created_at: int
    created_by: str
    file_type: str = "formal"


class WorkspaceFileListResponse(ResponseModel):
    data: list[WorkspaceFileItem]
    total: int
    has_more: bool


class BatchDeleteRequest(BaseModel):
    file_ids: list[str] = Field(..., min_length=1)


class BatchDeleteResponse(ResponseModel):
    deleted_count: int
    failed_ids: list[str] = []


def reg(cls: type[BaseModel]):
    console_ns.schema_model(cls.__name__, cls.model_json_schema(ref_template=DEFAULT_REF_TEMPLATE_SWAGGER_2_0))


reg(WorkspaceFileListQuery)
reg(WorkspaceFileItem)
reg(WorkspaceFileListResponse)
reg(BatchDeleteRequest)
reg(BatchDeleteResponse)


@console_ns.route("/workspaces/current/files")
class WorkspaceFileListApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.expect(console_ns.models[WorkspaceFileListQuery.__name__])
    @console_ns.response(200, "Success", console_ns.models[WorkspaceFileListResponse.__name__])
    def get(self):
        current_user, current_tenant_id = current_account_with_tenant()
        payload = request.args.to_dict(flat=True)
        args = WorkspaceFileListQuery.model_validate(payload)

        stmt = (
            select(UploadFile)
            .where(
                UploadFile.tenant_id == current_tenant_id,
                _workspace_visible_file_filter(current_tenant_id),
            )
            .order_by(UploadFile.created_at.desc())
        )

        if args.keyword:
            stmt = stmt.where(UploadFile.name.ilike(f"%{args.keyword}%"))

        if args.file_type:
            stmt = stmt.where(UploadFile.file_type == args.file_type)

        total_stmt = select(db.func.count()).select_from(stmt.subquery())
        total = db.session.scalar(total_stmt) or 0

        offset = (args.page - 1) * args.limit
        stmt = stmt.offset(offset).limit(args.limit + 1)

        files = db.session.scalars(stmt).all()
        has_more = len(files) > args.limit
        if has_more:
            files = files[:args.limit]

        data = []
        for f in files:
            data.append(
                WorkspaceFileItem(
                    id=str(f.id),
                    name=f.name,
                    size=f.size,
                    mime_type=f.mime_type,
                    created_at=int(f.created_at.timestamp()),
                    created_by=str(f.created_by),
                    file_type=f.file_type or "formal",
                )
            )

        return WorkspaceFileListResponse(data=data, total=total, has_more=has_more).model_dump(mode="json"), 200

    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.response(201, "File uploaded successfully", console_ns.models[WorkspaceFileItem.__name__])
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()

        if "file" not in request.files:
            raise NoFileUploadedError()

        if len(request.files) > 1:
            raise TooManyFilesError()

        file = request.files["file"]
        if not file.filename:
            raise FilenameNotExistsError()

        # Get file_type from form data, default to "formal" (uploaded from document management page)
        file_type = request.form.get("file_type", "formal")
        if file_type not in ("formal", "temporary"):
            file_type = "formal"

        try:
            upload_file = FileService(db.engine).upload_file(
                filename=file.filename,
                content=file.read(),
                mimetype=file.mimetype,
                user=current_user,
                storage_namespace=WORKSPACE_FILE_STORAGE_NAMESPACE,
                file_type=file_type,
            )
        except services.errors.file.FileTooLargeError as e:
            raise FileTooLargeError(e.description)
        except services.errors.file.UnsupportedFileTypeError:
            raise UnsupportedFileTypeError()

        return (
            WorkspaceFileItem(
                id=str(upload_file.id),
                name=upload_file.name,
                size=upload_file.size,
                mime_type=upload_file.mime_type,
                created_at=int(upload_file.created_at.timestamp()),
                created_by=str(upload_file.created_by),
                file_type=upload_file.file_type or "formal",
            ).model_dump(mode="json"),
            201,
        )


@console_ns.route("/workspaces/current/files/<uuid:file_id>")
class WorkspaceFileApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    def get(self, file_id):
        """Download file"""
        current_user, current_tenant_id = current_account_with_tenant()
        file_id_str = str(file_id)

        upload_file = db.session.scalar(
            select(UploadFile).where(
                UploadFile.id == file_id_str,
                UploadFile.tenant_id == current_tenant_id,
                _workspace_visible_file_filter(current_tenant_id),
            ).limit(1)
        )

        if not upload_file:
            raise NotFound("File not found")

        from extensions.ext_storage import storage

        content = storage.load_once(upload_file.key)

        import io

        # Use octet-stream so console clients treat the response as a binary download
        # (not JSON), while Content-Disposition still carries the original filename.
        return send_file(
            io.BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=upload_file.name,
        )

    @setup_required
    @login_required
    @account_initialization_required
    def delete(self, file_id):
        current_user, current_tenant_id = current_account_with_tenant()
        file_id_str = str(file_id)

        upload_file = db.session.scalar(
            select(UploadFile).where(
                UploadFile.id == file_id_str,
                UploadFile.tenant_id == current_tenant_id,
                _workspace_visible_file_filter(current_tenant_id),
            ).limit(1)
        )

        if not upload_file:
            raise NotFound("File not found")

        FileService(db.engine).delete_file(file_id_str)

        return {"result": "success"}, 200


@console_ns.route("/workspaces/current/files/batch-delete")
class WorkspaceFileBatchDeleteApi(Resource):
    @setup_required
    @login_required
    @account_initialization_required
    @console_ns.expect(console_ns.models[BatchDeleteRequest.__name__])
    @console_ns.response(200, "Batch delete completed", console_ns.models[BatchDeleteResponse.__name__])
    def post(self):
        current_user, current_tenant_id = current_account_with_tenant()

        payload = console_ns.payload or {}
        args = BatchDeleteRequest.model_validate(payload)

        file_ids = args.file_ids
        deleted_count = 0
        failed_ids = []

        for file_id in file_ids:
            try:
                upload_file = db.session.scalar(
                    select(UploadFile).where(
                        UploadFile.id == file_id,
                        UploadFile.tenant_id == current_tenant_id,
                        _workspace_visible_file_filter(current_tenant_id),
                    ).limit(1)
                )

                if not upload_file:
                    failed_ids.append(file_id)
                    continue

                FileService(db.engine).delete_file(file_id)
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete file {file_id}: {e}")
                failed_ids.append(file_id)

        return BatchDeleteResponse(deleted_count=deleted_count, failed_ids=failed_ids).model_dump(mode="json"), 200
