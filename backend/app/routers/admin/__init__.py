from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])

from app.routers.admin import users as _users  # noqa: E402
from app.routers.admin import sessions as _sessions  # noqa: E402
from app.routers.admin import monitoring as _monitoring  # noqa: E402
from app.routers.admin import audit as _audit  # noqa: E402

router.include_router(_users.router)
router.include_router(_sessions.router)
router.include_router(_monitoring.router)
router.include_router(_audit.router)

# Re-export endpoint functions for tests that import them directly.
from app.routers.admin.users import (  # noqa: E402, F401
    list_users,
    get_user,
    create_user,
    update_user,
    delete_user,
    reset_password,
    toggle_active,
)
from app.routers.admin.sessions import list_all_sessions, kill_session  # noqa: E402, F401
from app.routers.admin.monitoring import (  # noqa: E402, F401
    get_stats,
    get_system_info,
    get_storage_info,
)
from app.routers.admin.audit import get_audit_log, export_audit_log  # noqa: E402, F401
