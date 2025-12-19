"""
NewsNexus HTTP Server
An HTTP wrapper around the NewsNexus MCP server for external app integration.

Usage:
    python http_server.py                    # Run on default port 8000
    python http_server.py --port 3000        # Run on custom port
    uvicorn http_server:app --host 0.0.0.0   # Production with uvicorn

For Claude Desktop, add to config:
    {
        "mcpServers": {
            "news-nexus": {
                "url": "http://localhost:8000/sse"
            }
        }
    }
"""
import sys
import os
import json
import asyncio
import argparse
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

# Add parent directory to path to import from main.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

# Import existing NewsNexus functions (reuse existing logic)
from main import (
    handle_request, 
    get_articles, 
    get_top_news, 
    get_health, 
    get_metrics,
    logger
)

# =============================================================================
# FASTAPI APP SETUP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI app."""
    logger.info("NewsNexus HTTP Server starting...")
    yield
    logger.info("NewsNexus HTTP Server shutting down...")

app = FastAPI(
    title="NewsNexus MCP Server",
    description="HTTP wrapper for NewsNexus MCP server - enables external app integration",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for external app access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for MCP clients
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# MCP SSE ENDPOINT (For Claude Desktop HTTP integration)
# =============================================================================

# Store active SSE connections
active_connections: Dict[str, asyncio.Queue] = {}

@app.get("/sse")
async def sse_endpoint(request: Request):
    """
    Server-Sent Events endpoint for MCP over HTTP.
    Claude Desktop connects here for HTTP-based MCP.
    """
    client_id = str(id(request))
    message_queue: asyncio.Queue = asyncio.Queue()
    active_connections[client_id] = message_queue
    
    async def event_generator():
        try:
            # Send initial connection event
            yield f"event: endpoint\ndata: /mcp/{client_id}\n\n"
            
            # Keep connection alive and send responses
            while True:
                try:
                    # Wait for messages with timeout to send keepalives
                    message = await asyncio.wait_for(message_queue.get(), timeout=30.0)
                    yield f"event: message\ndata: {json.dumps(message)}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            # Cleanup
            if client_id in active_connections:
                del active_connections[client_id]
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@app.post("/mcp/{client_id}")
async def mcp_client_endpoint(client_id: str, request: Request):
    """Handle MCP JSON-RPC requests from a specific SSE client."""
    try:
        body = await request.json()
        
        # Process the request using existing handler
        response = handle_request(body)
        
        # If this client has an active SSE connection, queue the response
        if client_id in active_connections:
            await active_connections[client_id].put(response)
        
        # Also return as HTTP response
        return JSONResponse(content=response if response else {})
    
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        )
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        )

# =============================================================================
# SIMPLE MCP ENDPOINT (Direct HTTP POST)
# =============================================================================

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """
    Direct MCP JSON-RPC endpoint for simple HTTP POST access.
    
    Usage:
        curl -X POST http://localhost:8000/mcp \
            -H "Content-Type: application/json" \
            -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
    """
    try:
        body = await request.json()
        response = handle_request(body)
        return JSONResponse(content=response if response else {})
    
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        )
    except Exception as e:
        logger.error(f"Error handling MCP request: {e}")
        return JSONResponse(
            status_code=500,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        )

# =============================================================================
# REST API ENDPOINTS (Simple HTTP access)
# =============================================================================

@app.get("/api/health")
async def health_endpoint():
    """Health check endpoint."""
    return get_health()

@app.get("/api/metrics")
async def metrics_endpoint():
    """Get server metrics."""
    return get_metrics()

@app.get("/api/articles")
async def articles_endpoint(
    domain: str = Query(..., description="Domain to fetch articles from"),
    topic: Optional[str] = Query(None, description="Topic filter"),
    location: Optional[str] = Query(None, description="Location filter"),
    count: Optional[int] = Query(8, description="Number of articles"),
    lastNDays: Optional[int] = Query(15, description="Days to look back"),
    fast_mode: bool = Query(False, description="Fast mode (skip to Google News)")
):
    """
    Get articles from a specific domain.
    
    Example: /api/articles?domain=techcrunch.com&count=5&topic=ai
    """
    return get_articles(
        domain=domain,
        topic=topic,
        location=location,
        lastNDays=lastNDays,
        fast_mode=fast_mode,
        count=count
    )

@app.get("/api/top-news")
async def top_news_endpoint(
    count: Optional[int] = Query(8, description="Number of articles"),
    topic: Optional[str] = Query(None, description="Topic filter"),
    location: Optional[str] = Query(None, description="Location filter"),
    lastNDays: Optional[int] = Query(15, description="Days to look back")
):
    """
    Get top news from all configured priority domains.
    
    Example: /api/top-news?count=10&topic=ai
    """
    return get_top_news(
        count=count,
        topic=topic,
        location=location,
        lastNDays=lastNDays
    )

# =============================================================================
# ROOT AND INFO ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "NewsNexus MCP Server",
        "version": "2.0.0",
        "description": "HTTP wrapper for NewsNexus MCP server",
        "endpoints": {
            "mcp_sse": "GET /sse - SSE endpoint for Claude Desktop",
            "mcp_post": "POST /mcp - Direct MCP JSON-RPC",
            "rest_health": "GET /api/health - Health check",
            "rest_articles": "GET /api/articles?domain=... - Get articles",
            "rest_top_news": "GET /api/top-news - Get top news"
        },
        "claude_desktop_config": {
            "mcpServers": {
                "news-nexus": {
                    "url": "http://localhost:8000/sse"
                }
            }
        }
    }

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Run the HTTP server."""
    parser = argparse.ArgumentParser(description="NewsNexus HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    
    print(f"""
╔═══════════════════════════════════════════════════════════════════╗
║                    NewsNexus HTTP Server                         ║
╠═══════════════════════════════════════════════════════════════════╣
║  Server running at: http://{args.host}:{args.port}                         
║                                                                   ║
║  Endpoints:                                                       ║
║    • SSE (Claude Desktop): GET  /sse                              ║
║    • MCP JSON-RPC:         POST /mcp                              ║
║    • REST API:             GET  /api/articles?domain=...          ║
║    • REST API:             GET  /api/top-news?count=10            ║
║    • Health:               GET  /api/health                       ║
║                                                                   ║
║  For Claude Desktop, add to config:                               ║
║    "news-nexus": {{ "url": "http://localhost:{args.port}/sse" }}          
╚═══════════════════════════════════════════════════════════════════╝
""")
    
    uvicorn.run(
        "http_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )

if __name__ == "__main__":
    main()
