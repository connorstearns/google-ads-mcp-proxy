import os, httpx
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

PROXY_VERSION = "0.2.0"
MCP_URL = os.environ["MCP_BACKEND_URL"].rstrip("/") + "/"
MCP_KEY = os.environ["MCP_SHARED_KEY"]

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",  # <-- never forward
}

app = FastAPI()

def _filtered_headers(src: httpx.Headers) -> dict:
    # Copy safe headers from upstream response to client response
    return {k: v for k, v in src.items() if k.lower() not in HOP_BY_HOP}

def _filtered_request_headers(src: httpx.Headers) -> dict:
    """Forward client headers downstream, minus hop-by-hop/auth details."""

    allowed = {}
    for key, value in src.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP:
            continue
        if lowered in {"authorization", "host"}:
            # Replace with proxy credentials / let httpx manage Host.
            continue
        allowed[key] = value
    return allowed


def _backend_url(path: str, query: Optional[str] = None) -> str:
    base = MCP_URL + path if path else MCP_URL
    if query:
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{query}"
    return base

@app.get("/")
def health():
    return {
        "ok": True,
        "version": PROXY_VERSION,
        "backend_set": bool(MCP_URL),
        "auth_set": bool(MCP_KEY),
        "proxy_for": MCP_URL,
    }

@app.get("/whoami")
def whoami():
    return {"proxy_version": PROXY_VERSION, "proxy_for": MCP_URL}

@app.get("/.well-known/mcp.json")
async def discovery(req: Request):
    # Forward discovery GET to backend; do NOT copy hop-by-hop headers back
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _backend_url(".well-known/mcp.json", req.url.query or None),
            headers={
                **_filtered_request_headers(req.headers),
                "Authorization": f"Bearer {MCP_KEY}",
            },
        )
    # Let FastAPI compute content length; set media_type only
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
        headers=_filtered_headers(r.headers),
    )

@app.get("/mcp/tools")
async def list_tools(req: Request):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            _backend_url("mcp/tools", req.url.query or None),
            headers={
                **_filtered_request_headers(req.headers),
                "Authorization": f"Bearer {MCP_KEY}",
            },
        )
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
        headers=_filtered_headers(r.headers),
    )

@app.post("/{path:path}")
async def forward(path: str, req: Request):
    body = await req.body()

    # Build headers for backend: inject Bearer, pass MCP-Protocol-Version, and set content-type.
    fwd_headers = _filtered_request_headers(req.headers)
    content_type = req.headers.get("content-type", "application/json")
    fwd_headers["Content-Type"] = content_type
    fwd_headers["Authorization"] = f"Bearer {MCP_KEY}"

    async with httpx.AsyncClient(timeout=60) as client:
        backend_url = _backend_url(path, req.url.query or None)
        r = await client.post(backend_url, content=body, headers=fwd_headers)

    # Return exactly the backend body. DO NOT set content_length manually.
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
        headers=_filtered_headers(r.headers),
    )

# Optional: handle OPTIONS for CORS/preflight if you expose this publicly
@app.options("/{path:path}")
async def options(path: str):
    return JSONResponse({})
