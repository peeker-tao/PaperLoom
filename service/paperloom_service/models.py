"""Request/response models. Field names follow schemas/*.json."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RegisterDocumentRequest(BaseModel):
    library_id: str = Field(default="", alias="libraryId")
    item_key: str = Field(default="", alias="itemKey")
    attachment_key: str = Field(default="", alias="attachmentKey")
    pdf_path: str = Field(alias="pdfPath")
    title: str = ""
    file_hash: str = Field(default="", alias="fileHash")
    force: bool = False

    model_config = {"populate_by_name": True}

    @field_validator("pdf_path")
    @classmethod
    def _absolute(cls, value: str) -> str:
        if not value:
            raise ValueError("pdfPath is required")
        return value


class TranslateRequest(BaseModel):
    document_id: str = Field(alias="documentId")
    pages: list[int] | None = None
    model: str | None = None
    use_babeldoc: bool | None = Field(default=None, alias="useBabeldoc")
    force: bool = False
    stale_only: bool = Field(
        default=False,
        alias="staleOnly",
        description="re-translate only segments whose generation config changed",
    )

    model_config = {"populate_by_name": True}


class Selection(BaseModel):
    text: str
    page: int
    page_label: str = Field(default="", alias="pageLabel")
    rects: list[list[float]] = Field(default_factory=list)
    kind: Literal["text", "formula", "figure"] = "text"

    model_config = {"populate_by_name": True}


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatAttachment(BaseModel):
    """An image the user attached to a question.

    `dataUrl` is a `data:image/...;base64,...` URL. It travels to the model as an
    `image_url` part and is stored with the message so reopening the paper shows
    what was asked.
    """

    id: str = ""
    data_url: str = Field(default="", alias="dataUrl")
    caption: str = ""
    name: str = ""

    model_config = {"populate_by_name": True}


class ChatRequest(BaseModel):
    document_id: str = Field(alias="documentId")
    conversation_id: str | None = Field(default=None, alias="conversationId")
    scope: Literal["selection", "section", "paper"] = "selection"
    selection: Selection | None = None
    image: str | None = Field(
        default=None, description="data:image/... base64 Data URL for figure questions"
    )
    images: list[ChatAttachment] = Field(default_factory=list)
    model: str | None = None
    context_chars: int | None = Field(default=None, alias="contextChars")
    max_output_tokens: int | None = Field(default=None, alias="maxOutputTokens")
    messages: list[ChatMessage]

    model_config = {"populate_by_name": True}


class AnalysisRequest(BaseModel):
    kind: Literal["card", "experiment", "novelty", "limitations", "compare", "outline"]
    document_ids: list[str] = Field(alias="documentIds")
    selection: Selection | None = None
    model: str | None = None
    language: str = "zh"
    duration_minutes: int = Field(default=10, alias="durationMinutes")
    focus: str = ""

    model_config = {"populate_by_name": True}


class TermInput(BaseModel):
    document_id: str | None = Field(default=None, alias="documentId")
    source: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=200)
    scope: Literal["paper", "global"] = "paper"
    status: Literal["suggested", "confirmed"] = "confirmed"
    note: str = ""

    model_config = {"populate_by_name": True}


class TermPatch(BaseModel):
    target: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["suggested", "confirmed"] | None = None
    note: str | None = None


class SettingsPatch(BaseModel):
    base_url: str | None = Field(default=None, alias="baseUrl")
    translate_model: str | None = Field(default=None, alias="translateModel")
    chat_model: str | None = Field(default=None, alias="chatModel")
    analysis_model: str | None = Field(default=None, alias="analysisModel")
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")
    connect_timeout_seconds: float | None = Field(
        default=None, alias="connectTimeoutSeconds"
    )
    concurrency: int | None = None
    qps: float | None = None
    max_retries: int | None = Field(default=None, alias="maxRetries")
    context_chars: int | None = Field(default=None, alias="contextChars")
    max_output_tokens: int | None = Field(default=None, alias="maxOutputTokens")
    thinking: bool | None = None
    babeldoc_enabled: bool | None = Field(default=None, alias="babeldocEnabled")
    babeldoc_timeout: float | None = Field(
        default=None, ge=30, le=14400, alias="babeldocTimeout"
    )
    api_key: str | None = Field(default=None, alias="apiKey")

    model_config = {"populate_by_name": True}


class ReadingStatePatch(BaseModel):
    page: int | None = Field(default=None, ge=1)
    mode: Literal["original", "translated", "dual"] | None = None
    sidebar_width: int | None = Field(
        default=None, ge=200, le=1000, alias="sidebarWidth"
    )
    sidebar_open: bool | None = Field(default=None, alias="sidebarOpen")
    selection: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class PersistMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    document_id: str | None = Field(default=None, alias="documentId")
    conversation_id: str | None = Field(default=None, alias="conversationId")
    citations: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[ChatAttachment] = Field(default_factory=list)
    model: str = ""
    status: Literal["done", "failed", "cancelled", "streaming"] = "done"
    usage: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class SearchRequest(BaseModel):
    document_id: str = Field(alias="documentId")
    query: str
    limit: int = 8

    model_config = {"populate_by_name": True}


class ClientLogRequest(BaseModel):
    """Diagnostic lines from the plugin UI (which cannot write files itself)."""

    lines: list[str] = Field(default_factory=list)
    source: str = ""


class ExtractTermsRequest(BaseModel):
    document_id: str = Field(alias="documentId")
    model: str | None = None
    max_terms: int = Field(default=24, alias="maxTerms")

    model_config = {"populate_by_name": True}
