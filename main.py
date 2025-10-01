import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse, PlainTextResponse

# Config
MCP_URL = os.environ["MCP_BACKEND_URL"].rstrip("/") + "/"
MCP_KEY = os.environ["MCP_SHARED_KEY"]
MCP_PROTO_DEFAULT = os.getenv("MCP_PROTO_DEFAULT", "2024-11-05")

app = FastAPI()

@app.get("/")
def health():
    return {"ok": True, "proxy_for": MCP_URL}

# --- Optional: small debug helpers (safe to remove later) ---
@app.get("/headers", include_in_schema=False)
def headers(req: Request):
    return JSONResponse({"headers": dict(req.headers)})

@app.post("/echo", include_in_schema=False)
async def echo(req: Request):
    b = await req.body()
    return PlainTextResponse(b.decode("utf-8"), media_type="text/plain")

# --- Main JSON-RPC forwarder ---
@app.post("/")
async def forward(req: Request):
    # Read raw body once
    body = await req.body()

    # Build headers to forward to backend:
    # - Always inject Bearer <MCP_KEY> to the backend (app-level auth)
    # - Pass through incoming MCP-Protocol-Version so backend can mirror it back
    # - Keep JSON content-type
    fwd_headers = {
        "Authorization": f"Bearer {MCP_KEY}",
        "Content-Type": "application/json",
    }
    in_mcp = req.headers.get("MCP-Protocol-Version")
    if in_mcp:
        fwd_headers["MCP-Protocol-Version"] = in_mcp

    # Forward to backend verbatim
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        backend = await client.post(MCP_URL, headers=fwd_headers, content=body)

    # Build a passthrough response
    # - Preserve backend content, status, and headers
    # - Ensure MCP-Protocol-Version is present on the response we send back
    out_headers = {}
    # Keep backend content-type if provided; otherwise default to JSON
    ct = backend.headers.get("content-type", "application/json")
    out_headers["Content-Type"] = ct

    # Prefer backend's header; otherwise mirror request's or default
    out_mcp = (
        backend.headers.get("MCP-Protocol-Version")
        or in_mcp
        or MCP_PROTO_DEFAULT
    )
    out_headers["MCP-Protocol-Version"] = out_mcp

    # Also useful pass-throughs (harmless, optional)
    for h in ("Cache-Control", "Vary", "ETag"):
        if h in backend.headers:
            out_headers[h] = backend.headers[h]

    # IMPORTANT: return the raw body (don’t JSON-encode again)
    return Response(
        content=backend.content,
        status_code=backend.status_code,
        headers=out_headers,
        media_type=None,  # already set via headers
    )
