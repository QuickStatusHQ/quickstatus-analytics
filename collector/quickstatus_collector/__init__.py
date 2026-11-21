"""The QuickStatus.dev analytics collector: every step that sees a visitor's IP address or user
agent. See PRIVACY.md. The QuickStatus.dev service runs this package unmodified and supplies
only the salt store, the queue and the geo database file."""

from .app import Collector, DailySalt, create_app
from .events import Beacon, BeaconError, enrich, parse_beacon, visitor_id

__version__ = "0.1.0"
__all__ = ["Beacon", "BeaconError", "Collector", "DailySalt", "create_app", "enrich", "parse_beacon", "visitor_id"]
