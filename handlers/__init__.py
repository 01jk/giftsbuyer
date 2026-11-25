from .start import router as start_router
from .catalog import router as catalog_router
from .gift_flow import router as gift_flow_router
from .admin import router as admin_router
from .buy_stars import router as buy_stars_router
from .channel_events import router as channel_events_router
from .partner import router as partner_router
from .support import router as support_router

__all__ = [
    "start_router",
    "catalog_router",
    "gift_flow_router",
    "admin_router",
    "buy_stars_router",
    "channel_events_router",
    "partner_router",
    "support_router"
]
