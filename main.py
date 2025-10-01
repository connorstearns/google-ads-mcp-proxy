import os, httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

MCP_URL = os.environ["MCP_BACKEND_URL"].rstrip("/")  # no trailing slash
MCP_KEY = os.environ["MCP_SHARED_KEY"]
PROXY_VERSION = os.getenv("PROXY_VERSION", "0.2.0")

app = FastAPI()

def _auth_headers():
    return {
        "Authorization": f"Bearer {MCP_KEY}",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": os.getenv("MCP_PROTO_DEFAULT", "2024-11-05"),
    }

@app.get("/")
async def health():
    return {
        "ok": True,
        "version": PROXY_VERSION,
        "backend_set": bool(MCP_URL),
        "auth_set": bool(MCP_KEY),
        "proxy_for": MCP_URL + "/",
    }

@app.get("/whoami")
async def whoami():
    return {"proxy_version": PROXY_VERSION, "proxy_for": MCP_URL + "/"}

# --- Discovery passthroughs (GET) ---
@app.get("/.well-known/mcp.json")
async def discovery():
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(MCP_URL + "/.well-known/mcp.json", headers=_auth_headers())
    return JSONResponse(status_code=r.status_code, content=r.json())

@app.get("/mcp/tools")
async def tools_list():
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(MCP_URL + "/mcp/tools", headers=_auth_headers())
    return JSONResponse(status_code=r.status_code, content=r.json())

# --- JSON-RPC passthrough (POST /) ---
@app.post("/")
async def forward(req: Request):
    body = await req.body()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(MCP_URL + "/", content=body, headers=_auth_headers())
    # pass through JSON (or text if backend error isn’t JSON)
    try:
        return JSONResponse(status_code=r.status_code, content=r.json())
    except Exception:
        return JSONResponse(status_code=r.status_code, content={"detail": r.text})
