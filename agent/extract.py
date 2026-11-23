from typing import Any

from agent import llm
from schema import AppResearch

SCHEMA = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string"},
        "auth_methods": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "OAuth2",
                    "API key",
                    "Basic",
                    "Bearer token",
                    "Personal access token",
                    "JWT",
                    "Signed request",
                    "Other",
                    "Unknown",
                ],
            },
        },
        "access": {
            "type": "string",
            "enum": [
                "self-serve",
                "free-tier",
                "paid-plan",
                "admin-approval",
                "contact-sales",
                "partner",
                "unknown",
            ],
        },
        "api_documented": {"type": "boolean"},
        "api_type": {
            "type": "string",
            "enum": ["REST", "GraphQL", "both", "none", "unknown"],
        },
        "api_breadth": {
            "type": "string",
            "enum": ["small", "medium", "broad", "unknown"],
        },
        "mcp": {
            "type": "string",
            "enum": ["none", "official", "community", "unknown"],
        },
        "buildability": {
            "type": "string",
            "enum": ["yes", "with-work", "no", "unknown"],
        },
        "blocker": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": [
        "one_liner",
        "auth_methods",
        "access",
        "api_documented",
        "api_type",
        "api_breadth",
        "mcp",
        "buildability",
        "blocker",
        "confidence",
    ],
}

SYSTEM = (
    "You are a precise SaaS API researcher. Extract facts ONLY from the provided documentation "
    "excerpts, but fill EVERY field. If the excerpts do not state something, use 'unknown' from "
    "the allowed enum; never leave a field blank. Definitions: "
    "one_liner = what the product/company does in general for its users (use your own knowledge "
    "of the brand); do NOT describe a specific plugin or integration. "
    "auth_methods = how API requests authenticate (e.g. OAuth2, API key). "
    "access = how a developer gets API credentials: self-serve (instant/free signup), "
    "free-tier (free but needs signup or a dev account), paid-plan, admin-approval, "
    "contact-sales, partner. "
    "api_documented = true if public API documentation is visible in the excerpts. "
    "api_type = REST, GraphQL, both or none. api_breadth = small, medium or broad. "
    "mcp = official/community/none MCP server if mentioned, else unknown. "
    "buildability = yes if an agent toolkit can be built today, with-work if partially, no if blocked. "
    "blocker = short phrase on the main blocker for an agent toolkit (empty if none). "
    "confidence = number between 0 and 1. For auth_methods, use only the exact allowed labels; "
    "normalize variants such as 'Basic Auth' to 'Basic' and 'API Key' to 'API key'. "
    "Use 'Other' for auth mechanisms without a matching allowed label."
)

_AUTH_METHODS = {
    "oauth": "OAuth2",
    "oauth 2": "OAuth2",
    "oauth2": "OAuth2",
    "api key": "API key",
    "apikey": "API key",
    "basic": "Basic",
    "basic auth": "Basic",
    "basic authentication": "Basic",
    "http basic auth": "Basic",
    "bearer": "Bearer token",
    "bearer token": "Bearer token",
    "personal access token": "Personal access token",
    "jwt": "JWT",
    "signed request": "Signed request",
    "unknown": "Unknown",
    "other": "Other",
}


def extract(app: dict[str, Any], docs: dict[str, Any]) -> AppResearch:
    user = (
        f"App: {app['name']}\n"
        f"Category: {app['category']}\n"
        f"Hint: {app.get('hint', '')}\n\n"
        f"Documentation excerpts:\n{docs.get('text', '')}\n"
    )
    data = llm.chat_json(SYSTEM, user, schema=SCHEMA)
    data.setdefault("name", app["name"])
    data.setdefault("category", app["category"])
    data["evidence_urls"] = docs.get("urls", [])
    auth_methods = data.get("auth_methods")
    if isinstance(auth_methods, list):
        data["auth_methods"] = [
            _AUTH_METHODS.get(method.strip().casefold(), "Other")
            if isinstance(method, str)
            else "Other"
            for method in auth_methods
        ]
    return AppResearch(**data)
