"""
Property name resolution with fuzzy matching.

Enables LLMs to reference properties by natural language names
rather than requiring exact property IDs.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from .config import get_config
from .ga_client import GAClient, GAProperty, get_ga_client


@dataclass
class PropertyMatch:
    """Result of a property name search."""
    property: GAProperty
    confidence: float
    matched_on: str  # "exact", "alias", "fuzzy"

    def to_dict(self) -> Dict:
        return {
            "property_id": self.property.id,
            "property_name": self.property.name,
            "display_name": self.property.display_name,
            "confidence": round(self.confidence, 3),
            "matched_on": self.matched_on,
        }


class PropertyResolver:
    """
    Resolves property names to GA4 property IDs with fuzzy matching.

    Supports:
    - Exact matches on property ID
    - Exact matches on property name
    - Custom user-defined aliases
    - Fuzzy matching with configurable threshold
    """

    def __init__(
        self,
        client: Optional[GAClient] = None,
        fuzzy_threshold: Optional[float] = None,
        custom_aliases: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize the property resolver.

        Args:
            client: GA client instance (uses global if not provided)
            fuzzy_threshold: Minimum similarity score for fuzzy matches (0.0-1.0)
            custom_aliases: Dict mapping property names to list of aliases
        """
        self.client = client or get_ga_client()
        config = get_config()
        self.fuzzy_threshold = fuzzy_threshold or config.fuzzy_threshold
        self.custom_aliases = custom_aliases or config.custom_aliases
        self._properties: Optional[List[GAProperty]] = None

    async def _ensure_properties_loaded(self) -> None:
        """Ensure properties are loaded from the GA API."""
        if self._properties is None:
            self._properties = await self.client.discover_properties()

    async def resolve(self, query: str) -> Optional[PropertyMatch]:
        """
        Resolve a query string to a GA4 property.

        Attempts resolution in order:
        1. Exact match on property ID
        2. Exact match on property name (case-insensitive)
        3. Match on display name (case-insensitive)
        4. Match on custom alias
        5. Fuzzy match on name/display name

        Args:
            query: The property name, ID, or alias to resolve

        Returns:
            PropertyMatch if found, None otherwise
        """
        await self._ensure_properties_loaded()

        if not self._properties:
            return None

        query_lower = query.lower().strip()
        query_clean = "".join(c for c in query_lower if c.isalnum())

        # 1. Exact match on property ID
        for prop in self._properties:
            if prop.id == query:
                return PropertyMatch(
                    property=prop, confidence=1.0, matched_on="exact_id"
                )

        # 2. Exact match on property name (cleaned)
        for prop in self._properties:
            if prop.name == query_clean:
                return PropertyMatch(
                    property=prop, confidence=1.0, matched_on="exact_name"
                )

        # 3. Match on display name
        for prop in self._properties:
            if prop.display_name.lower() == query_lower:
                return PropertyMatch(
                    property=prop, confidence=1.0, matched_on="display_name"
                )

        # 4. Match on custom aliases
        for prop_name, aliases in self.custom_aliases.items():
            if query_lower in [a.lower() for a in aliases]:
                # Find the property with this name
                for prop in self._properties:
                    if prop.name == prop_name or prop.display_name.lower() == prop_name.lower():
                        return PropertyMatch(
                            property=prop, confidence=1.0, matched_on="alias"
                        )

        # 5. Fuzzy matching
        best_match: Optional[Tuple[GAProperty, float, str]] = None

        for prop in self._properties:
            # Try matching against name
            name_score = SequenceMatcher(None, query_clean, prop.name).ratio()
            if name_score > self.fuzzy_threshold:
                if best_match is None or name_score > best_match[1]:
                    best_match = (prop, name_score, "fuzzy_name")

            # Try matching against display name
            display_clean = "".join(
                c for c in prop.display_name.lower() if c.isalnum()
            )
            display_score = SequenceMatcher(None, query_clean, display_clean).ratio()
            if display_score > self.fuzzy_threshold:
                if best_match is None or display_score > best_match[1]:
                    best_match = (prop, display_score, "fuzzy_display")

            # Try partial matching (query contained in name)
            if query_clean in prop.name or query_clean in display_clean:
                partial_score = len(query_clean) / max(len(prop.name), len(display_clean))
                if partial_score > 0.3:  # At least 30% match
                    effective_score = 0.7 + (partial_score * 0.3)  # Scale to 0.7-1.0
                    if best_match is None or effective_score > best_match[1]:
                        best_match = (prop, effective_score, "partial")

        if best_match:
            return PropertyMatch(
                property=best_match[0],
                confidence=best_match[1],
                matched_on=best_match[2],
            )

        return None

    async def search(self, query: str, max_results: int = 5) -> List[PropertyMatch]:
        """
        Search for properties matching a query.

        Returns multiple matches ranked by confidence.

        Args:
            query: The search query
            max_results: Maximum number of results to return

        Returns:
            List of PropertyMatch objects sorted by confidence
        """
        await self._ensure_properties_loaded()

        if not self._properties:
            return []

        query_lower = query.lower().strip()
        query_clean = "".join(c for c in query_lower if c.isalnum())

        matches: List[PropertyMatch] = []

        for prop in self._properties:
            # Check for exact matches
            if prop.id == query or prop.name == query_clean:
                matches.append(
                    PropertyMatch(property=prop, confidence=1.0, matched_on="exact")
                )
                continue

            # Calculate fuzzy score
            name_score = SequenceMatcher(None, query_clean, prop.name).ratio()
            display_clean = "".join(
                c for c in prop.display_name.lower() if c.isalnum()
            )
            display_score = SequenceMatcher(None, query_clean, display_clean).ratio()

            best_score = max(name_score, display_score)

            # Also check partial matches
            if query_clean in prop.name or query_clean in display_clean:
                partial_score = 0.7 + (len(query_clean) / max(len(prop.name), len(display_clean), 1)) * 0.3
                best_score = max(best_score, partial_score)

            if best_score > 0.3:  # Lower threshold for search
                matches.append(
                    PropertyMatch(
                        property=prop,
                        confidence=best_score,
                        matched_on="fuzzy" if best_score < 1.0 else "exact",
                    )
                )

        # Sort by confidence and limit results
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:max_results]

    async def get_property_id(self, query: str) -> Optional[str]:
        """
        Convenience method to get just the property ID for a query.

        Args:
            query: The property name, ID, or alias

        Returns:
            Property ID if found, None otherwise
        """
        match = await self.resolve(query)
        return match.property.id if match else None

    async def list_all(self) -> List[GAProperty]:
        """
        Get all available properties.

        Returns:
            List of all GA4 properties accessible to the service account
        """
        await self._ensure_properties_loaded()
        return self._properties or []

    def clear_cache(self) -> None:
        """Clear the cached property list."""
        self._properties = None


# Global resolver instance
_resolver: Optional[PropertyResolver] = None


def get_property_resolver() -> PropertyResolver:
    """Get the global property resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = PropertyResolver()
    return _resolver


def reset_property_resolver() -> None:
    """Reset the global property resolver."""
    global _resolver
    _resolver = None
