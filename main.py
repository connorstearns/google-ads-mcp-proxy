import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse, PlainTextResponse

MCP_URL = os.environ["MCP_BACKEND_URL"].rstrip("/") + "/"
MCP_KEY = os.environ["MCP_SHARED_KEY"]
MCP_PROTO_DEFAULT = os.getenv("MCP_PROTO_DEFAULT", "2024-11-05")

app = FastAPI()

# --- ALWAYS add MCP-Protocol-Version to every response ---
@app.middleware("http")
async def ensure_mcp_header(request: Request, call_next):
    resp = await call_next(request)
    # If the downstream handler didn't set it, add it here.
    if "MCP-Protocol-Version" not in resp.headers:
        resp.headers["MCP-Protocol-Version"] = (
            request.headers.get("MCP-Protocol-Version") or MCP_PROTO_DEFAULT
        )
    # Make sure JSON RPC responses keep JSON content-type
    if request.method == "POST" and request.url.path == "/":
        # Only enforce on the JSON-RPC endpoint
        ct = resp.headers.get("content-type", "")
        if "application/json" not in ct.lower():
            resp.headers["content-type"] = "application/json"
    return resp

@app.get("/")
def health():
    # Health is fine to keep simple; middleware will still add MCP-Protocol-Version
    return {"ok": True, "proxy_for": MCP_URL}

# --- Debug helpers ---
@app.get("/headers", include_in_schema=False)
def headers(req: Request):
    # Shows headers the PROXY received from the client
    return JSONResponse({"headers": dict(req.headers)})

@app.post("/echo", include_in_schema=False)
async def echo(req: Request):
    # Echos request body as text
    b = await req.body()
    return PlainTextResponse(b.decode("utf-8"), media_type="text/plain")

@app.get("/via", include_in_schema=False)
async def via(req: Request):
    # Calls backend /headers so you can see what the BACKEND received
    fwd_headers = {
        "Authorization": f"Bearer {MCP_KEY}",
        "MCP-Protocol-Version": req.headers.get("MCP-Protocol-Version", MCP_PROTO_DEFAULT),
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30)) as client:
        r = await client.get(MCP_URL.rstrip("/") + "/headers", headers=fwd_headers)
    return Response(content=r.content, status_code=r.status_code, headers={"content-type": "application/json"})

# --- JSON-RPC forwarder ---
@app.post("/")
async def forward(req: Request):
    body = await req.body()

    # Forward auth + MCP header + JSON content-type to backend
    fwd_headers = {
        "Authorization": f"Bearer {MCP_KEY}",
        "Content-Type": "application/json",
    }
    in_mcp = req.headers.get("MCP-Protocol-Version")
    if in_mcp:
        fwd_headers["MCP-Protocol-Version"] = in_mcp

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        backend = await client.post(MCP_URL, headers=fwd_headers, content=body)

    # Return backend response AS-IS (don’t JSON-encode again)
    out_headers = {}
    out_headers["Content-Type"] = backend.headers.get("content-type", "application/json")

    # Prefer backend’s MCP header; otherwise mirror request’s or default
    out_headers["MCP-Protocol-Version"] = (
        backend.headers.get("MCP-Protocol-Version")
        or in_mcp
        or MCP_PROTO_DEFAULT
    )

    # Optional passthroughs
    for h in ("Cache-Control", "Vary", "ETag"):
        if h in backend.headers:
            out_headers[h] = backend.headers[h]

    return Response(
        content=backend.content,
        status_code=backend.status_code,
        headers=out_headers,
    )
