"""
GA Multi MCP - Google Analytics 4 Multi-Property MCP Server

An MCP server for querying Google Analytics 4 data across multiple properties,
designed for use with LLM agents and the Programmatic Tool Calling (PTC) framework.
"""

__version__ = "0.1.0"
__author__ = "Hey Good Game"

from .server import main, mcp

__all__ = ["main", "mcp", "__version__"]
