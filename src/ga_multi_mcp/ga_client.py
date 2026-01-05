"""
Google Analytics 4 API client with caching and multi-property support.

Provides a clean interface for querying GA4 data with automatic
property discovery and caching to minimize API calls.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    FilterExpressionList,
    Metric,
    NumericValue,
    OrderBy,
    RunRealtimeReportRequest,
    RunReportRequest,
)
from google.api_core.exceptions import GoogleAPIError
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from .config import get_config

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached value with expiration time."""
    data: Any
    expires_at: float

    def is_valid(self) -> bool:
        return datetime.now().timestamp() < self.expires_at


@dataclass
class GAProperty:
    """Represents a GA4 property."""
    id: str
    name: str
    display_name: str
    account_id: str
    website_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "account_id": self.account_id,
            "website_url": self.website_url,
        }


@dataclass
class GAMetadata:
    """Metadata for a GA4 property including available dimensions and metrics."""
    property_id: str
    dimensions: List[Dict[str, Any]]
    metrics: List[Dict[str, Any]]
    custom_dimensions: List[Dict[str, Any]] = field(default_factory=list)
    custom_metrics: List[Dict[str, Any]] = field(default_factory=list)


class GAClientError(Exception):
    """Raised when GA API operations fail."""
    pass


class GAClient:
    """
    Google Analytics 4 API client with caching.

    Provides methods for property discovery, metadata retrieval,
    and data querying across multiple GA4 properties.
    """

    def __init__(self, credentials_path: Optional[str] = None):
        """
        Initialize the GA client.

        Args:
            credentials_path: Path to service account JSON. If not provided,
                            uses the path from configuration.
        """
        config = get_config()
        self.credentials_path = credentials_path or config.credentials_path
        self.cache_ttl = config.cache_ttl
        self.property_cache_ttl = config.property_cache_ttl

        self._data_client: Optional[BetaAnalyticsDataClient] = None
        self._admin_client = None
        self._cache: Dict[str, CacheEntry] = {}
        self._initialized = False

    def _initialize(self) -> None:
        """Initialize Google API clients lazily."""
        if self._initialized:
            return

        try:
            credentials = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=[
                    "https://www.googleapis.com/auth/analytics.readonly",
                    "https://www.googleapis.com/auth/analytics.manage.users.readonly",
                ],
            )

            self._data_client = BetaAnalyticsDataClient(credentials=credentials)
            self._admin_client = build(
                "analyticsadmin",
                "v1beta",
                credentials=credentials,
                cache_discovery=False,
            )
            self._initialized = True

        except Exception as e:
            raise GAClientError(f"Failed to initialize GA client: {e}")

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get a value from cache if valid."""
        if entry := self._cache.get(key):
            if entry.is_valid():
                return entry.data
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """Set a value in cache with TTL."""
        ttl = ttl or self.cache_ttl
        expires_at = datetime.now().timestamp() + ttl
        self._cache[key] = CacheEntry(data=data, expires_at=expires_at)

    async def discover_properties(self) -> List[GAProperty]:
        """
        Discover all GA4 properties accessible to the service account.

        Returns:
            List[GAProperty]: List of accessible properties

        Raises:
            GAClientError: If discovery fails
        """
        cache_key = "properties"
        if cached := self._get_cached(cache_key):
            return cached

        self._initialize()

        try:
            properties = []

            # List all accounts
            accounts_response = self._admin_client.accounts().list().execute()

            for account in accounts_response.get("accounts", []):
                account_name = account.get("name", "")
                account_id = account_name.split("/")[-1] if account_name else ""

                # Get properties for this account
                props_response = (
                    self._admin_client.properties()
                    .list(filter=f"parent:{account_name}")
                    .execute()
                )

                for prop in props_response.get("properties", []):
                    prop_name = prop.get("name", "")
                    prop_id = prop_name.split("/")[-1] if prop_name else ""
                    display_name = prop.get("displayName", "")

                    # Create clean name for matching
                    clean_name = "".join(
                        c for c in display_name.lower() if c.isalnum()
                    )[:30]

                    properties.append(
                        GAProperty(
                            id=prop_id,
                            name=clean_name,
                            display_name=display_name,
                            account_id=account_id,
                            website_url=prop.get("websiteUrl"),
                        )
                    )

            self._set_cached(cache_key, properties, self.property_cache_ttl)
            logger.info(f"Discovered {len(properties)} GA4 properties")
            return properties

        except GoogleAPIError as e:
            raise GAClientError(f"Failed to discover properties: {e}")

    async def get_metadata(self, property_id: str) -> GAMetadata:
        """
        Get available dimensions and metrics for a property.

        Args:
            property_id: The GA4 property ID

        Returns:
            GAMetadata: Available dimensions and metrics

        Raises:
            GAClientError: If metadata retrieval fails
        """
        cache_key = f"metadata:{property_id}"
        if cached := self._get_cached(cache_key):
            return cached

        self._initialize()

        try:
            metadata = self._data_client.get_metadata(
                name=f"properties/{property_id}/metadata"
            )

            dimensions = []
            custom_dimensions = []
            for dim in metadata.dimensions:
                dim_info = {
                    "api_name": dim.api_name,
                    "ui_name": dim.ui_name,
                    "description": dim.description,
                    "custom": dim.custom_definition,
                }
                if dim.custom_definition:
                    custom_dimensions.append(dim_info)
                else:
                    dimensions.append(dim_info)

            metrics = []
            custom_metrics = []
            for metric in metadata.metrics:
                metric_info = {
                    "api_name": metric.api_name,
                    "ui_name": metric.ui_name,
                    "description": metric.description,
                    "custom": metric.custom_definition,
                }
                if metric.custom_definition:
                    custom_metrics.append(metric_info)
                else:
                    metrics.append(metric_info)

            result = GAMetadata(
                property_id=property_id,
                dimensions=dimensions,
                metrics=metrics,
                custom_dimensions=custom_dimensions,
                custom_metrics=custom_metrics,
            )

            self._set_cached(cache_key, result, self.property_cache_ttl)
            return result

        except GoogleAPIError as e:
            raise GAClientError(f"Failed to get metadata for property {property_id}: {e}")

    async def run_report(
        self,
        property_id: str,
        metrics: List[str],
        start_date: str,
        end_date: str,
        dimensions: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
        order_by: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Run a GA4 report.

        Args:
            property_id: The GA4 property ID
            metrics: List of metric names (e.g., ["activeUsers", "sessions"])
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            dimensions: Optional list of dimension names
            filters: Optional list of filter conditions
            order_by: Optional ordering specification
            limit: Maximum rows to return

        Returns:
            Dict containing report data with rows, headers, and metadata

        Raises:
            GAClientError: If the report fails
        """
        self._initialize()

        try:
            request = RunReportRequest(
                property=f"properties/{property_id}",
                metrics=[Metric(name=m) for m in metrics],
                date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
                limit=limit,
            )

            if dimensions:
                request.dimensions = [Dimension(name=d) for d in dimensions]

            if filters:
                request.dimension_filter = self._build_filter_expression(filters)

            if order_by:
                request.order_bys = [self._build_order_by(order_by, metrics)]

            response = self._data_client.run_report(request=request)

            # Format response
            rows = []
            dimension_headers = [h.name for h in response.dimension_headers]
            metric_headers = [h.name for h in response.metric_headers]

            for row in response.rows:
                row_data = {}

                for i, dim_value in enumerate(row.dimension_values):
                    row_data[dimension_headers[i]] = dim_value.value

                for i, metric_value in enumerate(row.metric_values):
                    value = metric_value.value
                    # Try to convert to number
                    try:
                        if "." in value:
                            row_data[metric_headers[i]] = float(value)
                        else:
                            row_data[metric_headers[i]] = int(value)
                    except ValueError:
                        row_data[metric_headers[i]] = value

                rows.append(row_data)

            return {
                "property_id": property_id,
                "date_range": {"start_date": start_date, "end_date": end_date},
                "dimensions": dimension_headers,
                "metrics": metric_headers,
                "rows": rows,
                "row_count": len(rows),
                "total_rows": response.row_count,
            }

        except GoogleAPIError as e:
            raise GAClientError(f"Report failed for property {property_id}: {e}")

    async def run_realtime_report(
        self,
        property_id: str,
        metrics: Optional[List[str]] = None,
        dimensions: Optional[List[str]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        Run a realtime GA4 report (last 30 minutes).

        Args:
            property_id: The GA4 property ID
            metrics: Optional list of metrics (defaults to activeUsers)
            dimensions: Optional list of dimensions
            limit: Maximum rows to return

        Returns:
            Dict containing realtime data

        Raises:
            GAClientError: If the report fails
        """
        self._initialize()

        if not metrics:
            metrics = ["activeUsers"]

        try:
            request = RunRealtimeReportRequest(
                property=f"properties/{property_id}",
                metrics=[Metric(name=m) for m in metrics],
                limit=limit,
            )

            if dimensions:
                request.dimensions = [Dimension(name=d) for d in dimensions]

            response = self._data_client.run_realtime_report(request=request)

            # Format response
            rows = []
            dimension_headers = [h.name for h in response.dimension_headers]
            metric_headers = [h.name for h in response.metric_headers]

            for row in response.rows:
                row_data = {}

                for i, dim_value in enumerate(row.dimension_values):
                    row_data[dimension_headers[i]] = dim_value.value

                for i, metric_value in enumerate(row.metric_values):
                    value = metric_value.value
                    try:
                        if "." in value:
                            row_data[metric_headers[i]] = float(value)
                        else:
                            row_data[metric_headers[i]] = int(value)
                    except ValueError:
                        row_data[metric_headers[i]] = value

                rows.append(row_data)

            return {
                "property_id": property_id,
                "lookback_minutes": 30,
                "dimensions": dimension_headers,
                "metrics": metric_headers,
                "rows": rows,
                "row_count": len(rows),
            }

        except GoogleAPIError as e:
            raise GAClientError(f"Realtime report failed for property {property_id}: {e}")

    def _build_filter_expression(
        self, filters: List[Dict[str, Any]]
    ) -> FilterExpression:
        """Build a filter expression from a list of filter conditions."""
        if len(filters) == 1:
            return FilterExpression(filter=self._build_single_filter(filters[0]))

        filter_expressions = [
            FilterExpression(filter=self._build_single_filter(f)) for f in filters
        ]
        return FilterExpression(
            and_group=FilterExpressionList(expressions=filter_expressions)
        )

    def _build_single_filter(self, filter_spec: Dict[str, Any]) -> Filter:
        """Build a single filter from a specification."""
        field = filter_spec.get("field", "")
        operator = filter_spec.get("operator", "EXACT").upper()
        value = filter_spec.get("value", "")

        filter_obj = Filter(field_name=field)

        if operator in ("EXACT", "CONTAINS", "BEGINS_WITH", "ENDS_WITH", "REGEXP"):
            match_type_map = {
                "EXACT": Filter.StringFilter.MatchType.EXACT,
                "CONTAINS": Filter.StringFilter.MatchType.CONTAINS,
                "BEGINS_WITH": Filter.StringFilter.MatchType.BEGINS_WITH,
                "ENDS_WITH": Filter.StringFilter.MatchType.ENDS_WITH,
                "REGEXP": Filter.StringFilter.MatchType.FULL_REGEXP,
            }
            filter_obj.string_filter = Filter.StringFilter(
                match_type=match_type_map[operator], value=str(value)
            )
        elif operator in ("GREATER_THAN", "LESS_THAN", "EQUAL"):
            op_map = {
                "GREATER_THAN": Filter.NumericFilter.Operation.GREATER_THAN,
                "LESS_THAN": Filter.NumericFilter.Operation.LESS_THAN,
                "EQUAL": Filter.NumericFilter.Operation.EQUAL,
            }
            filter_obj.numeric_filter = Filter.NumericFilter(
                operation=op_map[operator],
                value=NumericValue(double_value=float(value)),
            )
        elif operator == "IN_LIST":
            values = value if isinstance(value, list) else [value]
            filter_obj.in_list_filter = Filter.InListFilter(
                values=[str(v) for v in values]
            )

        return filter_obj

    def _build_order_by(
        self, order_spec: Dict[str, Any], metrics: List[str]
    ) -> OrderBy:
        """Build an order by specification."""
        field = order_spec.get("field", "")
        desc = order_spec.get("desc", True)

        if field in metrics:
            return OrderBy(metric=OrderBy.MetricOrderBy(metric_name=field), desc=desc)
        else:
            return OrderBy(
                dimension=OrderBy.DimensionOrderBy(dimension_name=field), desc=desc
            )

    def clear_cache(self, pattern: Optional[str] = None) -> int:
        """
        Clear cached data.

        Args:
            pattern: Optional pattern to match cache keys (e.g., "metadata:")
                    If not provided, clears all cache.

        Returns:
            int: Number of cache entries cleared
        """
        if pattern is None:
            count = len(self._cache)
            self._cache.clear()
            return count

        keys_to_remove = [k for k in self._cache if pattern in k]
        for key in keys_to_remove:
            del self._cache[key]
        return len(keys_to_remove)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = datetime.now().timestamp()
        valid_entries = sum(1 for e in self._cache.values() if e.is_valid())

        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries,
            "cache_keys": list(self._cache.keys()),
        }


# Global client instance (lazy loaded)
_client: Optional[GAClient] = None


def get_ga_client() -> GAClient:
    """Get the global GA client instance."""
    global _client
    if _client is None:
        _client = GAClient()
    return _client


def reset_ga_client() -> None:
    """Reset the global GA client (useful for testing)."""
    global _client
    _client = None
