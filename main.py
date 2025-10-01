# proxy/main.py
import os, uuid, json, httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

MCP_URL  = os.environ["MCP_BACKEND_URL"].rstrip("/")  # e.g. https://mcp-google-ads-...run.app
MCP_KEY  = os.environ["MCP_SHARED_KEY"]
PROTO    = os.getenv("MCP_PROTO_DEFAULT", "2024-11-05")

app = FastAPI()

def _auth_headers(extra: dict | None = None) -> dict:
    h = {
        "Authorization": f"Bearer {MCP_KEY}",
        "MCP-Protocol-Version": PROTO,
    }
    if extra:
        h.update(extra)
    return h

def _client() -> httpx.AsyncClient:
    # generous but bounded timeouts; Cloud Run default request timeout is higher
    return httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0, read=25.0))

@app.get("/")
async def health():
    return {"ok": True, "proxy_for": MCP_URL}

@app.get("/.well-known/mcp.json")
async def discovery():
    # Forward with auth so the client "sees" the gated tools
    async with _client() as client:
        r = await client.get(f"{MCP_URL}/.well-known/mcp.json", headers=_auth_headers())
    # Pass through status/headers + JSON
    try:
        data = r.json()
        return JSONResponse(status_code=r.status_code, content=data, headers={"MCP-Protocol-Version": PROTO})
    except Exception:
        return PlainTextResponse(r.text, status_code=r.status_code)

@app.post("/")
async def rpc(req: Request):
    body = await req.body()
    trace_id = str(uuid.uuid4())
    fwd_headers = _auth_headers({"Content-Type": "application/json", "X-Trace-Id": trace_id})

    async with _client() as client:
        r = await client.post(f"{MCP_URL}/", content=body, headers=fwd_headers)

    # make sure we always return application/json when upstream is JSON
    try:
        content = r.json()
        # add trace id into result (non-invasive)
        if isinstance(content, dict) and "result" in content and isinstance(content["result"], dict):
            # append tiny diagnostic crumb the client can ignore
            result = content["result"]
            if "content" in result and isinstance(result["content"], list):
                result["content"].append({"type": "json", "json": {"_trace": trace_id}})
        return JSONResponse(status_code=r.status_code, content=content, headers={"MCP-Protocol-Version": PROTO})
    except Exception:
        return PlainTextResponse(r.text, status_code=r.status_code)

# Optional: tiny echo for debugging the proxy layer only
@app.post("/echo")
async def echo(req: Request):
    body = await req.json()
    return {"ok": True, "you_sent": body}
