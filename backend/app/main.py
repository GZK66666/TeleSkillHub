import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

import rarfile
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "mysql+pymysql://root:123456@localhost:3306/teleskillhub?charset=utf8mb4"
)
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "./data_storage")).resolve()
UPLOAD_DIR = STORAGE_ROOT / "uploads"
GENERATED_DIR = STORAGE_ROOT / "generated"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

VISIBILITY_OPTIONS = {"public", "department", "user"}

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    visibility_type: Mapped[str] = mapped_column(String(20), default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SkillPermission(Base):
    __tablename__ = "skill_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    scope_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer)
    archive_name: Mapped[str] = mapped_column(String(255))
    extracted_path: Mapped[str] = mapped_column(String(500))
    changelog: Mapped[Optional[str]] = mapped_column(Text)
    security_score: Mapped[int] = mapped_column(Integer, default=100)
    security_report: Mapped[Optional[dict]] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SkillFile(Base):
    __tablename__ = "skill_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("skill_versions.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(500))
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False)
    size: Mapped[int] = mapped_column(Integer, default=0)
    content_preview: Mapped[Optional[str]] = mapped_column(Text)


class SkillDownload(Base):
    __tablename__ = "skill_downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"))
    version_id: Mapped[int] = mapped_column(ForeignKey("skill_versions.id", ondelete="CASCADE"))
    downloaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    downloaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


app = FastAPI(title="TeleSkillHub API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CurrentUser(BaseModel):
    id: int
    department_id: int
    is_admin: bool


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    x_user_id: Optional[int] = Header(default=None), db: Session = Depends(get_db)
) -> CurrentUser:
    user_id = x_user_id or 1
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")
    return CurrentUser(id=user.id, department_id=user.department_id, is_admin=user.is_admin)


def ensure_visible(skill: Skill, user: CurrentUser, db: Session) -> None:
    if user.is_admin or skill.owner_id == user.id or skill.visibility_type == "public":
        return
    perms = db.query(SkillPermission).filter(SkillPermission.skill_id == skill.id).all()
    for p in perms:
        if p.scope_type == "user" and p.target_id == user.id:
            return
        if p.scope_type == "department" and p.target_id == user.department_id:
            return
    raise HTTPException(status_code=403, detail="No permission for this skill")


def _is_safe_target(base_dir: Path, target_name: str) -> bool:
    safe_target = (base_dir / target_name).resolve()
    return str(safe_target).startswith(str(base_dir.resolve()))


def extract_archive(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.infolist():
                if not _is_safe_target(destination, member.filename):
                    raise HTTPException(status_code=400, detail="Unsafe path in archive")
            zf.extractall(destination)
        return
    if suffix == ".rar":
        with rarfile.RarFile(archive_path) as rf:
            for member in rf.infolist():
                if not _is_safe_target(destination, member.filename):
                    raise HTTPException(status_code=400, detail="Unsafe path in archive")
            rf.extractall(destination)
        return
    raise HTTPException(status_code=400, detail="Only zip or rar files are supported")


def create_zip_from_directory(source_dir: Path, destination_zip: Path) -> None:
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(source_dir)))


def build_file_index(version_id: int, root_dir: Path, db: Session) -> None:
    db.query(SkillFile).filter(SkillFile.version_id == version_id).delete()
    for item in sorted(root_dir.rglob("*")):
        rel_path = str(item.relative_to(root_dir))
        is_dir = item.is_dir()
        preview = None
        size = 0
        if item.is_file():
            size = item.stat().st_size
            if size < 1024 * 200:
                preview = item.read_text(encoding="utf-8", errors="ignore")[:4000]
        db.add(
            SkillFile(
                version_id=version_id,
                path=rel_path,
                is_dir=is_dir,
                size=size,
                content_preview=preview,
            )
        )
    db.commit()


def run_security_check(root_dir: Path) -> tuple[int, dict]:
    blocked_ext = {".exe", ".dll", ".bat", ".cmd", ".ps1"}
    risky_patterns = [r"subprocess", r"rm\s+-rf", r"eval\(", r"os\.system", r"curl\s+http"]
    issues: list[dict] = []
    score = 100

    for path in root_dir.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() in blocked_ext:
            issues.append({"file": str(path.name), "severity": "high", "message": "Blocked extension"})
            score -= 20
        if path.stat().st_size > 2 * 1024 * 1024:
            issues.append({"file": str(path.name), "severity": "medium", "message": "Large file"})
            score -= 5

        if path.suffix.lower() in {".py", ".js", ".sh", ".md", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in risky_patterns:
                if re.search(pattern, text, flags=re.IGNORECASE):
                    issues.append(
                        {
                            "file": str(path.name),
                            "severity": "medium",
                            "message": f"Matched risky pattern: {pattern}",
                        }
                    )
                    score -= 8

    return max(score, 0), {"issues": issues, "checked_at": datetime.utcnow().isoformat()}


def _apply_permissions(skill_id: int, departments: str, users: str, db: Session) -> None:
    db.query(SkillPermission).filter(SkillPermission.skill_id == skill_id).delete()
    dep_ids = [int(x) for x in departments.split(",") if x.strip().isdigit()]
    user_ids = [int(x) for x in users.split(",") if x.strip().isdigit()]

    for dep_id in dep_ids:
        db.add(SkillPermission(skill_id=skill_id, scope_type="department", target_id=dep_id))
    for uid in user_ids:
        db.add(SkillPermission(skill_id=skill_id, scope_type="user", target_id=uid))
    db.commit()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/skills")
def list_skills(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    skills = db.query(Skill).order_by(Skill.updated_at.desc()).all()
    result = []
    for s in skills:
        try:
            ensure_visible(s, user, db)
        except HTTPException:
            continue
        latest = (
            db.query(SkillVersion)
            .filter(SkillVersion.skill_id == s.id)
            .order_by(SkillVersion.version_no.desc())
            .first()
        )
        downloads = db.query(SkillDownload).filter(SkillDownload.skill_id == s.id).count()
        result.append(
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "visibility_type": s.visibility_type,
                "latest_version": latest.version_no if latest else 0,
                "security_score": latest.security_score if latest else None,
                "download_count": downloads,
            }
        )
    return result


@app.get("/skills/{skill_id}")
def skill_detail(
    skill_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> dict:
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    ensure_visible(skill, user, db)

    versions = (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill_id)
        .order_by(SkillVersion.version_no.desc())
        .all()
    )
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "visibility_type": skill.visibility_type,
        "versions": [
            {
                "id": v.id,
                "version_no": v.version_no,
                "archive_name": v.archive_name,
                "changelog": v.changelog,
                "security_score": v.security_score,
                "security_report": v.security_report,
                "created_at": v.created_at,
            }
            for v in versions
        ],
    }


@app.get("/skills/{skill_id}/versions/{version_id}/files")
def version_files(
    skill_id: int, version_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[dict]:
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    ensure_visible(skill, user, db)

    rows = db.query(SkillFile).filter(SkillFile.version_id == version_id).order_by(SkillFile.path.asc()).all()
    return [{"id": r.id, "path": r.path, "is_dir": r.is_dir, "size": r.size} for r in rows]


@app.get("/skills/{skill_id}/versions/{version_id}/files/content")
def file_content(
    skill_id: int,
    version_id: int,
    path: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    ensure_visible(skill, user, db)

    row = (
        db.query(SkillFile)
        .filter(SkillFile.version_id == version_id, SkillFile.path == path)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "path": row.path,
        "is_dir": row.is_dir,
        "size": row.size,
        "content_preview": row.content_preview,
    }


@app.post("/skills/upload")
def upload_skill(
    name: str = Form(...),
    description: str = Form(""),
    visibility_type: str = Form("public"),
    departments: str = Form(""),
    users: str = Form(""),
    changelog: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    if visibility_type not in VISIBILITY_OPTIONS:
        raise HTTPException(status_code=400, detail="Invalid visibility_type")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".zip", ".rar"}:
        raise HTTPException(status_code=400, detail="Only zip/rar allowed")

    skill = db.query(Skill).filter(Skill.name == name).first()
    if not skill:
        skill = Skill(
            name=name,
            description=description,
            owner_id=current_user.id,
            visibility_type=visibility_type,
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)
    elif skill.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only owner/admin can publish new versions")

    skill.description = description
    skill.visibility_type = visibility_type
    db.commit()

    next_version = (
        (db.query(func.max(SkillVersion.version_no)).filter(SkillVersion.skill_id == skill.id).scalar() or 0)
        + 1
    )

    archive_name = f"skill_{skill.id}_v{next_version}{suffix}"
    archive_path = UPLOAD_DIR / archive_name
    with archive_path.open("wb") as out:
        out.write(file.file.read())

    version_dir = UPLOAD_DIR / f"skill_{skill.id}" / f"v{next_version}"
    if version_dir.exists():
        shutil.rmtree(version_dir)

    try:
        extract_archive(archive_path, version_dir)
    except rarfile.Error as exc:
        raise HTTPException(status_code=400, detail=f"RAR extraction failed: {exc}") from exc

    security_score, report = run_security_check(version_dir)

    version = SkillVersion(
        skill_id=skill.id,
        version_no=next_version,
        archive_name=archive_name,
        extracted_path=str(version_dir),
        changelog=changelog,
        security_score=security_score,
        security_report=report,
        created_by=current_user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    _apply_permissions(skill.id, departments, users, db)
    build_file_index(version.id, version_dir, db)
    return {
        "skill_id": skill.id,
        "version_id": version.id,
        "version_no": next_version,
        "security_score": security_score,
        "security_report": report,
    }


@app.post("/skills/{skill_id}/rollback/{version_no}")
def rollback(
    skill_id: int,
    version_no: int,
    changelog: str = Form(""),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.owner_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only owner/admin can rollback")

    source = (
        db.query(SkillVersion)
        .filter(SkillVersion.skill_id == skill_id, SkillVersion.version_no == version_no)
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Version not found")

    next_version = (
        (db.query(func.max(SkillVersion.version_no)).filter(SkillVersion.skill_id == skill.id).scalar() or 0)
        + 1
    )
    target_dir = UPLOAD_DIR / f"skill_{skill.id}" / f"v{next_version}"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(Path(source.extracted_path), target_dir)

    archive_name = f"skill_{skill.id}_v{next_version}.zip"
    archive_path = UPLOAD_DIR / archive_name
    create_zip_from_directory(target_dir, archive_path)

    new_version = SkillVersion(
        skill_id=skill.id,
        version_no=next_version,
        archive_name=archive_name,
        extracted_path=str(target_dir),
        changelog=changelog or f"Rollback to version {version_no}",
        security_score=source.security_score,
        security_report=source.security_report,
        created_by=current_user.id,
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    build_file_index(new_version.id, target_dir, db)

    return {"message": "rollback success", "new_version_no": next_version, "version_id": new_version.id}


@app.get("/skills/{skill_id}/download/{version_id}")
def download_skill(
    skill_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    skill = db.get(Skill, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    ensure_visible(skill, current_user, db)

    version = db.get(SkillVersion, version_id)
    if not version or version.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="Version not found")

    archive_path = UPLOAD_DIR / version.archive_name
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")

    db.add(SkillDownload(skill_id=skill_id, version_id=version_id, downloaded_by=current_user.id))
    db.commit()
    return FileResponse(path=archive_path, filename=version.archive_name, media_type="application/octet-stream")


@app.get("/leaderboard/downloads")
def leaderboard(db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    rows = (
        db.query(Skill.id, Skill.name, func.count(SkillDownload.id).label("downloads"))
        .join(SkillDownload, SkillDownload.skill_id == Skill.id)
        .group_by(Skill.id, Skill.name)
        .order_by(func.count(SkillDownload.id).desc())
        .limit(20)
        .all()
    )
    return [{"skill_id": r.id, "name": r.name, "downloads": int(r.downloads)} for r in rows]


@app.post("/skills/generate")
def generate_skill(
    skill_name: str = Form(...),
    requirement: str = Form(...),
    output_format: str = Form("anthropic"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    if output_format != "anthropic":
        raise HTTPException(status_code=400, detail="Only anthropic format is supported")

    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", skill_name).strip("-").lower()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid skill name")

    out_dir = GENERATED_DIR / f"{safe_name}-{int(datetime.utcnow().timestamp())}"
    (out_dir / "references").mkdir(parents=True, exist_ok=True)

    skill_md = f"""---
name: {skill_name}
summary: Auto-generated initial skill
format: anthropic-skill-v1
---

# {skill_name}

## Purpose
{requirement}

## Usage
1. Clarify input context.
2. Execute steps defined in this skill.
3. Return a concise and auditable output.

## Workflow
- Understand requirement boundaries.
- Break task into atomic steps.
- Produce result and self-check.

## Output Contract
- Structured markdown response.
- Include assumptions and next actions.
"""
    (out_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    ref_md = """# references

- domain-notes.md: Add internal policy or glossary here.
- examples.md: Add good input/output examples here.
"""
    (out_dir / "references" / "README.md").write_text(ref_md, encoding="utf-8")

    archive_path = shutil.make_archive(str(out_dir), "zip", root_dir=out_dir)
    return {"generated_dir": str(out_dir), "download_archive": archive_path}


app.mount("/storage", StaticFiles(directory=str(STORAGE_ROOT)), name="storage")
