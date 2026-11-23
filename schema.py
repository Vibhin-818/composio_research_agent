from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

AuthMethod = Literal[
    "OAuth2",
    "API key",
    "Basic",
    "Bearer token",
    "Personal access token",
    "JWT",
    "Signed request",
    "Other",
    "Unknown",
]

AccessTier = Literal[
    "self-serve",
    "free-tier",
    "paid-plan",
    "admin-approval",
    "contact-sales",
    "partner",
    "unknown",
]

ApiType = Literal["REST", "GraphQL", "both", "none", "unknown"]
ApiBreadth = Literal["small", "medium", "broad", "unknown"]
McpStatus = Literal["none", "official", "community", "unknown"]
BuildVerdict = Literal["yes", "with-work", "no", "unknown"]
Status = Literal["ok", "needs-human", "error"]


class AppResearch(BaseModel):
    name: str
    category: str
    one_liner: str = ""
    auth_methods: list[AuthMethod] = Field(default_factory=list)
    access: AccessTier = "unknown"
    auth_notes: str = ""
    api_documented: bool = False
    api_type: ApiType = "unknown"
    api_breadth: ApiBreadth = "unknown"
    mcp: McpStatus = "unknown"
    mcp_url: Optional[str] = None
    buildability: BuildVerdict = "unknown"
    blocker: str = ""
    evidence_urls: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        if value is None:
            return 0.0
        value = float(value)
        if value > 1:
            value = value / 100
        return max(0.0, min(1.0, value))


class AppRecord(BaseModel):
    id: int
    status: Status = "ok"
    research: Optional[AppResearch] = None
    first_pass_research: Optional[AppResearch] = None
    verification: dict = Field(default_factory=dict)
    error: Optional[str] = None
