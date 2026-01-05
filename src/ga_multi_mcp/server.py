"""
GA Multi MCP Server - Google Analytics 4 Multi-Property MCP Server

An MCP server providing tools for querying Google Analytics 4 data
across multiple properties with fuzzy name matching.
"""

import logging
import sys
from typing import Annotated, Any, Dict, List, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from .config import ConfigError, get_config
from .date_parser import DateParseError, get_date_range_description, parse_date_range
from .ga_client import GAClientError, get_ga_client
from .property_resolver import get_property_resolver

# Configure logging to stderr (stdout reserved for MCP protocol)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("google.auth").setLevel(logging.ERROR)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

# Initialize FastMCP server
mcp = FastMCP(
    name="GA Multi MCP",
    instructions="""
    Google Analytics 4 Multi-Property MCP Server.

    This server provides tools for querying GA4 analytics data across multiple
    properties. It supports fuzzy property name matching, natural language dates,
    and multi-property comparisons.

    Start by using list_properties to discover available GA4 properties,
    then use query_analytics to fetch data.

    Common metrics: activeUsers, sessions, screenPageViews, eventCount, bounceRate
    Common dimensions: date, country, city, deviceCategory, browser, pagePath
    """,
)


@mcp.tool
async def list_properties() -> Dict[str, Any]:
    """
    List all accessible GA4 properties.

    Use this first to discover available properties before querying.
    Returns property IDs, names, and display names that can be used
    with other tools.

    Returns:
        Dict with 'properties' list and 'count'
    """
    try:
        resolver = get_property_resolver()
        properties = await resolver.list_all()

        return {
            "properties": [p.to_dict() for p in properties],
            "count": len(properties),
        }
    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")
    except GAClientError as e:
        raise ToolError(f"Failed to list properties: {e}")


@mcp.tool
async def search_properties(
    query: Annotated[str, Field(description="Search query (property name, partial name, or keyword)")]
) -> Dict[str, Any]:
    """
    Search for properties by name with fuzzy matching.

    Use this when you're not sure of the exact property name.
    Returns multiple matches ranked by confidence score.

    Args:
        query: Search query to match against property names

    Returns:
        Dict with 'matches' list and 'best_match'
    """
    try:
        resolver = get_property_resolver()
        matches = await resolver.search(query, max_results=5)

        result = {
            "query": query,
            "matches": [m.to_dict() for m in matches],
            "count": len(matches),
        }

        if matches:
            result["best_match"] = matches[0].to_dict()

        return result
    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")
    except GAClientError as e:
        raise ToolError(f"Search failed: {e}")


@mcp.tool
async def query_analytics(
    property: Annotated[str, Field(description="Property name, ID, or alias (fuzzy matching supported)")],
    metrics: Annotated[List[str], Field(description="Metrics to query (e.g., ['activeUsers', 'sessions'])")],
    start_date: Annotated[str, Field(description="Start date (YYYY-MM-DD, 'today', 'yesterday', '7daysAgo', etc.)")],
    end_date: Annotated[str, Field(description="End date (YYYY-MM-DD, 'today', 'yesterday', etc.)")],
    dimensions: Annotated[Optional[List[str]], Field(description="Dimensions to group by (e.g., ['date', 'country'])")] = None,
    filters: Annotated[Optional[List[Dict[str, Any]]], Field(description="Filter conditions [{field, operator, value}]")] = None,
    order_by: Annotated[Optional[Dict[str, Any]], Field(description="Ordering {field: str, desc: bool}")] = None,
    limit: Annotated[int, Field(description="Maximum rows to return", ge=1, le=10000)] = 1000,
) -> Dict[str, Any]:
    """
    Query GA4 analytics data for a single property.

    Supports fuzzy property name matching, natural language dates,
    and flexible filtering. Returns structured data suitable for analysis.

    Args:
        property: Property identifier (supports fuzzy matching)
        metrics: List of GA4 metrics to retrieve
        start_date: Query start date
        end_date: Query end date
        dimensions: Optional dimensions for grouping
        filters: Optional filter conditions
        order_by: Optional ordering specification
        limit: Maximum rows (default 1000)

    Returns:
        Dict with query results including rows, metadata, and date range
    """
    try:
        # Resolve property name
        resolver = get_property_resolver()
        match = await resolver.resolve(property)

        if not match:
            # Get suggestions
            suggestions = await resolver.search(property, max_results=3)
            suggestion_names = [s.property.display_name for s in suggestions]
            raise ToolError(
                f"Property '{property}' not found. "
                f"Did you mean: {', '.join(suggestion_names) if suggestion_names else 'No similar properties found'}"
            )

        # Parse dates
        try:
            start, end = parse_date_range(start_date, end_date)
        except DateParseError as e:
            raise ToolError(str(e))

        # Run query
        client = get_ga_client()
        result = await client.run_report(
            property_id=match.property.id,
            metrics=metrics,
            start_date=start,
            end_date=end,
            dimensions=dimensions,
            filters=filters,
            order_by=order_by,
            limit=limit,
        )

        # Add property resolution info
        result["property_name"] = match.property.display_name
        result["property_match"] = {
            "confidence": match.confidence,
            "matched_on": match.matched_on,
        }
        result["date_range_description"] = get_date_range_description(start, end)

        return result

    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")
    except GAClientError as e:
        raise ToolError(f"Query failed: {e}")


@mcp.tool
async def query_multiple_properties(
    properties: Annotated[List[str], Field(description="List of property names or IDs to query")],
    metrics: Annotated[List[str], Field(description="Metrics to query across all properties")],
    start_date: Annotated[str, Field(description="Start date for all queries")],
    end_date: Annotated[str, Field(description="End date for all queries")],
    dimensions: Annotated[Optional[List[str]], Field(description="Optional dimensions for grouping")] = None,
) -> Dict[str, Any]:
    """
    Query the same metrics across multiple properties for comparison.

    Useful for comparing performance across different sites/apps.
    Returns aggregated results with per-property breakdowns.

    Args:
        properties: List of property identifiers
        metrics: Metrics to retrieve from each property
        start_date: Query start date
        end_date: Query end date
        dimensions: Optional dimensions

    Returns:
        Dict with results per property and aggregated summary
    """
    try:
        # Parse dates
        try:
            start, end = parse_date_range(start_date, end_date)
        except DateParseError as e:
            raise ToolError(str(e))

        resolver = get_property_resolver()
        client = get_ga_client()

        results = []
        errors = []
        totals: Dict[str, float] = {m: 0 for m in metrics}

        for prop_name in properties:
            match = await resolver.resolve(prop_name)

            if not match:
                errors.append({
                    "property": prop_name,
                    "error": "Property not found",
                })
                continue

            try:
                result = await client.run_report(
                    property_id=match.property.id,
                    metrics=metrics,
                    start_date=start,
                    end_date=end,
                    dimensions=dimensions,
                    limit=1000,
                )

                # Calculate totals from first row (summary)
                if result["rows"] and not dimensions:
                    for metric in metrics:
                        if metric in result["rows"][0]:
                            val = result["rows"][0][metric]
                            if isinstance(val, (int, float)):
                                totals[metric] += val

                results.append({
                    "property_id": match.property.id,
                    "property_name": match.property.display_name,
                    "data": result["rows"],
                    "row_count": result["row_count"],
                })

            except GAClientError as e:
                errors.append({
                    "property": match.property.display_name,
                    "error": str(e),
                })

        return {
            "date_range": {
                "start_date": start,
                "end_date": end,
                "description": get_date_range_description(start, end),
            },
            "metrics": metrics,
            "dimensions": dimensions or [],
            "results": results,
            "errors": errors if errors else None,
            "summary": {
                "properties_queried": len(properties),
                "properties_successful": len(results),
                "totals": totals if not dimensions else None,
            },
        }

    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")


@mcp.tool
async def get_property_metadata(
    property: Annotated[str, Field(description="Property name or ID")]
) -> Dict[str, Any]:
    """
    Get available dimensions and metrics for a GA4 property.

    Use this to discover what data is available before querying.
    Includes both standard and custom dimensions/metrics.

    Args:
        property: Property identifier

    Returns:
        Dict with dimensions, metrics, and custom fields
    """
    try:
        resolver = get_property_resolver()
        match = await resolver.resolve(property)

        if not match:
            raise ToolError(f"Property '{property}' not found")

        client = get_ga_client()
        metadata = await client.get_metadata(match.property.id)

        return {
            "property_id": match.property.id,
            "property_name": match.property.display_name,
            "dimensions": metadata.dimensions,
            "metrics": metadata.metrics,
            "custom_dimensions": metadata.custom_dimensions,
            "custom_metrics": metadata.custom_metrics,
            "total_dimensions": len(metadata.dimensions) + len(metadata.custom_dimensions),
            "total_metrics": len(metadata.metrics) + len(metadata.custom_metrics),
        }

    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")
    except GAClientError as e:
        raise ToolError(f"Failed to get metadata: {e}")


@mcp.tool
async def query_realtime(
    property: Annotated[str, Field(description="Property name or ID")],
    metrics: Annotated[Optional[List[str]], Field(description="Metrics to query (default: activeUsers)")] = None,
    dimensions: Annotated[Optional[List[str]], Field(description="Dimensions for grouping")] = None,
    limit: Annotated[int, Field(description="Maximum rows", ge=1, le=1000)] = 100,
) -> Dict[str, Any]:
    """
    Query real-time GA4 data (last 30 minutes).

    Returns current active users and other real-time metrics.
    Useful for monitoring live traffic.

    Args:
        property: Property identifier
        metrics: Metrics to query (defaults to activeUsers)
        dimensions: Optional dimensions
        limit: Maximum rows

    Returns:
        Dict with real-time data
    """
    try:
        resolver = get_property_resolver()
        match = await resolver.resolve(property)

        if not match:
            raise ToolError(f"Property '{property}' not found")

        client = get_ga_client()
        result = await client.run_realtime_report(
            property_id=match.property.id,
            metrics=metrics,
            dimensions=dimensions,
            limit=limit,
        )

        result["property_name"] = match.property.display_name

        return result

    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")
    except GAClientError as e:
        raise ToolError(f"Realtime query failed: {e}")


@mcp.tool
async def get_cache_status() -> Dict[str, Any]:
    """
    Get current cache status for debugging.

    Shows cached entries, their age, and hit/miss statistics.
    Useful for understanding API call patterns.

    Returns:
        Dict with cache statistics
    """
    try:
        client = get_ga_client()
        return client.get_cache_stats()
    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")


@mcp.tool
async def clear_cache(
    pattern: Annotated[Optional[str], Field(description="Optional pattern to match (e.g., 'metadata:', 'properties')")] = None
) -> Dict[str, Any]:
    """
    Clear cached data.

    Use to force fresh data retrieval from GA4 API.
    Can clear all cache or just entries matching a pattern.

    Args:
        pattern: Optional pattern to match cache keys

    Returns:
        Dict with number of entries cleared
    """
    try:
        client = get_ga_client()
        resolver = get_property_resolver()

        # Clear GA client cache
        cleared = client.clear_cache(pattern)

        # Also clear property resolver cache if clearing all
        if pattern is None:
            resolver.clear_cache()

        return {
            "cleared_entries": cleared,
            "pattern": pattern,
            "message": f"Cleared {cleared} cache entries" + (f" matching '{pattern}'" if pattern else ""),
        }
    except ConfigError as e:
        raise ToolError(f"Configuration error: {e}")


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
