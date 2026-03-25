from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from tools import (
    get_data_protection_document,
    get_recent_supreme_court_decisions,
    get_slovak_law,
    get_supreme_court_decision,
    list_legislation_years,
    search_data_protection_guidelines,
    search_slovak_legislation,
    search_supreme_court,
)

# ─────────────────────────────────────────────────────────────────────
# Server metadata
# ─────────────────────────────────────────────────────────────────────

INSTRUCTION_STRING = """Slovak Legal Sources MCP Server

This server provides natural-language access to three official Slovak legal data sources:

1. **Slovak Supreme Court** (Najvyssi sud) — 104,000+ court decisions covering civil,
   commercial, administrative, and criminal law. Searchable by keywords, ECLI, date range,
   and subject matter via the nsud.sk OpenData API.

2. **Slovak Collection of Laws** (Zbierka zakonov) — Legislation from 1918 to present,
   including laws, decrees, regulations, and constitutional acts from the official Slov-Lex portal.

3. **Slovak Data Protection Authority** (UOOU) — GDPR guidelines, methodological instructions,
   EDPB guidance translations, and data protection opinions.

Use the tools to search across these sources, retrieve full texts of laws and court decisions,
and stay up to date with Slovak legal developments."""

VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────
# Server configuration — NO authentication
# ─────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="Slovak Legal Sources",
    instructions=INSTRUCTION_STRING,
    version=VERSION,
)


# ─────────────────────────────────────────────────────────────────────
# Tools — all set to requires_permission: False for automatic execution
# ─────────────────────────────────────────────────────────────────────

# Supreme Court tools
mcp.tool(meta={"requires_permission": False})(search_supreme_court)
mcp.tool(meta={"requires_permission": False})(get_supreme_court_decision)
mcp.tool(meta={"requires_permission": False})(get_recent_supreme_court_decisions)

# Collection of Laws tools
mcp.tool(meta={"requires_permission": False})(search_slovak_legislation)
mcp.tool(meta={"requires_permission": False})(get_slovak_law)
mcp.tool(meta={"requires_permission": False})(list_legislation_years)

# Data Protection Authority tools
mcp.tool(meta={"requires_permission": False})(search_data_protection_guidelines)
mcp.tool(meta={"requires_permission": False})(get_data_protection_document)


# ─────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


# ─────────────────────────────────────────────────────────────────────
# ASGI app — run with: uvicorn server:app --host 0.0.0.0 --port 8000
# ─────────────────────────────────────────────────────────────────────

app = mcp.http_app()
