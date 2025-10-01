import os, httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

BACKEND = os.environ["MCP_BACKEND_URL"].rstrip("/")  # e.g. https://mcp-google-ads-...run.app
MCP_KEY  = os.environ["MCP_SHARED_KEY"]

app = FastAPI()

def _make_headers(in_headers):
    # Start with inbound headers, but force auth and ensure protocol header passes through.
    h = {k: v for k, v in in_headers.items()}
    h["Authorization"] = f"Bearer {MCP_KEY}"
    # Be explicit about JSON on POSTs; harmless on GETs.
    h["Content-Type"] = "application/json"
    return h

def _passthru_headers(upstream):
    # Return only safe/needed headers. Include MCP-Protocol-Version if backend sets it.
    allowed = {"content-type", "cache-control", "mcp-protocol-version"}
    return {k: v for k, v in upstream.headers.items() if k.lower() in allowed}

@app.get("/")
def health():
    return {"ok": True, "proxy_for": BACKEND}

# ---- GET passthroughs required by MCP clients ----
@app.get("/.well-known/mcp.json")
async def discovery(req: Request):
    url = f"{BACKEND}{req.url.path}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, headers=_make_headers(req.headers), params=req.query_params)
    return Response(content=r.content, status_code=r.status_code, headers=_passthru_headers(r))

@app.head("/.well-known/mcp.json")
async def discovery_head(req: Request):
    url = f"{BACKEND}{req.url.path}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.head(url, headers=_make_headers(req.headers), params=req.query_params)
    return Response(content=b"", status_code=r.status_code, headers=_passthru_headers(r))

@app.get("/mcp/tools")
async def tools(req: Request):
    url = f"{BACKEND}{req.url.path}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, headers=_make_headers(req.headers), params=req.query_params)
    return Response(content=r.content, status_code=r.status_code, headers=_passthru_headers(r))

# ---- JSON-RPC POST passthrough ----
@app.post("/")
async def forward(req: Request):
    body = await req.body()
    url = f"{BACKEND}/"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, content=body, headers=_make_headers(req.headers))
    # Try to keep JSON semantics; fall back to bytes if upstream wasn’t JSON
    try:
        return JSONResponse(status_code=r.status_code, content=r.json(), headers=_passthru_headers(r))
    except Exception:
        return Response(content=r.content, status_code=r.status_code, headers=_passthru_headers(r))
