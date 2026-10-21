from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from extensions.ext_database import db
from models.model import UploadFile
from extensions.ext_storage import storage
import io

app = FastAPI(title="Dify File Download API")


def get_current_tenant_id():
    """获取当前租户ID（从Flask上下文获取）"""
    from flask import request as flask_request
    from flask_login import current_user
    
    if not current_user.is_authenticated:
        raise HTTPException(status_code=401, detail="未认证")
    
    return current_user.current_tenant_id


@app.get("/api/files/{file_id}/download")
async def download_file(file_id: str, tenant_id: str = Depends(get_current_tenant_id)):
    """下载文件"""
    upload_file = db.session.scalar(
        select(UploadFile).where(
            UploadFile.id == file_id,
            UploadFile.tenant_id == tenant_id,
        ).limit(1)
    )

    if not upload_file:
        raise HTTPException(status_code=404, detail="文件未找到")

    try:
        content = storage.load_once(upload_file.key)
        
        return StreamingResponse(
            io.BytesIO(content),
            media_type=upload_file.mime_type or "application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename=\"{upload_file.name}\""
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件下载失败: {str(e)}")
