"""
NewsNexus MCP Client - Production Ready
Fetches top news using the NewsNexus MCP server via JSON-RPC.
"""

import json
import subprocess
import sys
import threading
import queue
import time
import os
from datetime import datetime


class MCPClient:
    """MCP Client with proper thread-based stdout reading."""
    
    def __init__(self, command: str, args: list, quiet_stderr: bool = True):
        # Suppress stderr output from server (logging)
        stderr_dest = subprocess.DEVNULL if quiet_stderr else subprocess.PIPE
        
        self.process = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_dest,
            text=True,
            bufsize=1
        )
        self.request_id = 0
        self.response_queue = queue.Queue()
        
        # Start background thread to read responses
        self.reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self.reader_thread.start()
    
    def _read_stdout(self):
        """Background thread to read stdout lines."""
        try:
            while True:
                line = self.process.stdout.readline()
                if not line:
                    break
                self.response_queue.put(line.strip())
        except:
            pass
    
    def send_request(self, method: str, params: dict = None, timeout: int = 60) -> dict:
        """Send a JSON-RPC request and wait for response."""
        self.request_id += 1
        
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        
        if params is not None:
            request["params"] = params
        
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line)
        self.process.stdin.flush()
        
        try:
            response_line = self.response_queue.get(timeout=timeout)
            return json.loads(response_line)
        except queue.Empty:
            raise TimeoutError(f"No response within {timeout} seconds")
    
    def initialize(self) -> dict:
        """Initialize the MCP session."""
        result = self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "NewsNexus-Client", "version": "1.0.0"}
        }, timeout=10)
        return result.get("result", {})
    
    def list_tools(self) -> list:
        """List available tools."""
        result = self.send_request("tools/list", timeout=5)
        return result.get("result", {}).get("tools", [])
    
    def call_tool(self, name: str, arguments: dict, timeout: int = 60) -> dict:
        """Call a tool and return parsed result."""
        result = self.send_request("tools/call", {
            "name": name,
            "arguments": arguments
        }, timeout=timeout)
        
        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0].get("text", "{}"))
        return result
    
    def close(self):
        """Close the connection."""
        try:
            self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=3)
        except:
            self.process.kill()


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f" {text} ".center(80, "="))
    print("=" * 80)


def main():
    """Main function to fetch news via MCP."""
    
    # MCP Server configuration (from mcp.json)
    MCP_COMMAND = r"C:\Swdtools\conda_envs\python_3.13\python.exe"
    MCP_ARGS = [r"C:\Sandbox\VSCode_Projects\NewsNexus\main.py"]
    
    print_header("NewsNexus MCP Client")
    
    client = None
    
    try:
        # Initialize
        print("\n🔌 Connecting to MCP server...")
        client = MCPClient(MCP_COMMAND, MCP_ARGS, quiet_stderr=True)
        
        init_result = client.initialize()
        server_name = init_result.get("serverInfo", {}).get("name", "Unknown")
        server_version = init_result.get("serverInfo", {}).get("version", "Unknown")
        print(f"   ✅ Connected to: {server_name} v{server_version}")
        
        # List tools
        print("\n📋 Available tools:")
        tools = client.list_tools()
        for tool in tools:
            print(f"   • {tool['name']}: {tool.get('description', '')[:50]}...")
        
        # Health check
        print("\n🏥 Server health:")
        health = client.call_tool("health_check", {}, timeout=5)
        print(f"   Status: {health.get('status', 'Unknown')}")
        print(f"   Domains configured: {health.get('domainCount', 0)}")
        print(f"   Cache size: {health.get('cache', {}).get('size', 0)} items")
        
        # Fetch top news
        print_header("Fetching Top 10 News")
        print("\n📰 Fetching from priority sources (may take 10-30s)...\n")
        
        start_time = time.time()
        news_result = client.call_tool("get_top_news", {"count": 10}, timeout=120)
        elapsed = time.time() - start_time
        
        articles = news_result.get("articles", [])
        sources_used = news_result.get("sources_used", [])
        server_duration = news_result.get("durationMs", 0)
        
        print(f"✅ Fetched {len(articles)} articles in {elapsed:.1f}s (server: {server_duration:.0f}ms)")
        
        # Display sources
        print(f"\n📊 Sources used ({len(sources_used)}):")
        for source in sources_used:
            print(f"   • {source}")
        
        # Display articles
        print(f"\n📰 Top {len(articles)} News Articles:")
        print("-" * 80)
        
        for i, article in enumerate(articles, 1):
            title = article.get('title', 'N/A')
            source = article.get('source_domain', 'N/A')
            published = article.get('published_at', 'N/A')
            url = article.get('url', 'N/A')
            
            # Truncate long URLs for display
            if len(url) > 70:
                display_url = url[:70] + "..."
            else:
                display_url = url
            
            print(f"\n{i}. {title}")
            print(f"   📍 Source: {source}")
            print(f"   🕐 Published: {published[:19] if published != 'N/A' else 'N/A'}")
            print(f"   🔗 {display_url}")
        
        print("\n" + "-" * 80)
        
        # Save to file
        output_file = f"mcp_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'news': news_result,
                'health': health,
                'fetched_at': datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Results saved to: {output_file}")
        print("\n✅ MCP session completed successfully!")
        
    except TimeoutError as e:
        print(f"\n❌ Timeout: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if client:
            client.close()
            print("🔌 MCP connection closed")


if __name__ == "__main__":
    main()
