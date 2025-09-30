import os, httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

MCP_URL = os.environ["MCP_BACKEND_URL"].rstrip("/") + "/"
MCP_KEY = os.environ["MCP_SHARED_KEY"]

app = FastAPI()

@app.get("/")
def health():
    return {"ok": True, "proxy_for": MCP_URL}

@app.post("/")
async def forward(req: Request):
    body = await req.body()
    headers = {"Authorization": f"Bearer {MCP_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(MCP_URL, content=body, headers=headers)
    # pass through JSON result (or error)
    try:
        return JSONResponse(status_code=r.status_code, content=r.json())
    except Exception:
        # fall back if backend didn't return JSON
        return PlainTextResponse(r.text, status_code=r.status_code)
