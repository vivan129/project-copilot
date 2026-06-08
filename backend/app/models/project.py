import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Integer, Text, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.db.session import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str | None] = mapped_column(String(100))
    difficulty_score: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    estimated_cost_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    estimated_hours: Mapped[int | None] = mapped_column(Integer)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="projects")  # noqa
    inputs: Mapped["ProjectInput"] = relationship("ProjectInput", back_populates="project", uselist=False)
    blueprint: Mapped["ProjectBlueprint"] = relationship("ProjectBlueprint", back_populates="project", uselist=False)
    parts: Mapped[list["ProjectPart"]] = relationship("ProjectPart", back_populates="project")
    code_files: Mapped[list["ProjectCode"]] = relationship("ProjectCode", back_populates="project")
    wiring: Mapped["ProjectWiring"] = relationship("ProjectWiring", back_populates="project", uselist=False)
    presentation: Mapped["ProjectPresentation"] = relationship("ProjectPresentation", back_populates="project", uselist=False)


class ProjectInput(Base):
    __tablename__ = "project_inputs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    skill_level: Mapped[str | None] = mapped_column(String(50))
    owned_components: Mapped[list | None] = mapped_column(JSONB)
    target_category: Mapped[str | None] = mapped_column(String(100))
    goals: Mapped[str | None] = mapped_column(Text)
    time_available: Mapped[str | None] = mapped_column(String(100))
    has_3d_printer: Mapped[bool] = mapped_column(Boolean, default=False)
    has_soldering: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_prompt: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship("Project", back_populates="inputs")


class ProjectBlueprint(Base):
    __tablename__ = "project_blueprints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    overview: Mapped[str | None] = mapped_column(Text)
    how_it_works: Mapped[str | None] = mapped_column(Text)
    difficulty_explanation: Mapped[str | None] = mapped_column(Text)
    build_phases: Mapped[list | None] = mapped_column(JSONB)
    common_mistakes: Mapped[list | None] = mapped_column(JSONB)
    safety_warnings: Mapped[list | None] = mapped_column(JSONB)
    next_level_ideas: Mapped[list | None] = mapped_column(JSONB)
    generation_model: Mapped[str | None] = mapped_column(String(100))
    generation_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    project: Mapped["Project"] = relationship("Project", back_populates="blueprint")


class ProjectPart(Base):
    __tablename__ = "project_parts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    component_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    estimated_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    already_owned: Mapped[bool] = mapped_column(Boolean, default=False)
    buy_links: Mapped[list | None] = mapped_column(JSONB)

    project: Mapped["Project"] = relationship("Project", back_populates="parts")


class ProjectCode(Base):
    __tablename__ = "project_code"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(255))
    code: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(100))

    project: Mapped["Project"] = relationship("Project", back_populates="code_files")


class ProjectWiring(Base):
    __tablename__ = "project_wiring"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    diagram_json: Mapped[dict | None] = mapped_column(JSONB)
    diagram_svg: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship("Project", back_populates="wiring")


class ProjectPresentation(Base):
    __tablename__ = "project_presentations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    how_it_works_layman: Mapped[str | None] = mapped_column(Text)
    technical_explanation: Mapped[str | None] = mapped_column(Text)
    judges_qa: Mapped[list | None] = mapped_column(JSONB)

    project: Mapped["Project"] = relationship("Project", back_populates="presentation")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(100))
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="usage_logs")
