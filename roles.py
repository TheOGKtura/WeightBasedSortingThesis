"""
Role-based permission system.

Permissions map directly to gui.py button object names.
Set True to enable, False to disable for each role.
"""

# ── Role Definitions ──
ROLES = {
    "admin": {
        "pushButton_start":     True,
        "pushButton_analytics": True,
        "pushButton_3":         True,
        "pushButton_home":      True,
        "pushButton_settings":  True,
        "pushButton_calibrate": True,
    },
    "user": {
        "pushButton_start":     True,
        "pushButton_analytics": True,
        "pushButton_3":         False,
        "pushButton_home":      True,
        "pushButton_settings":  False,
        "pushButton_calibrate": True,
    },
}

# ── User Accounts ──
USERS = {
    "wss-admin": {
        "password": "123456",
        "role":     "admin",
    },
    "operator-1": {
        "password": "123",
        "role":     "user",
    },
}

# ── Optional per-user production quotas (qualified item count per session) ──
# Set to None for no quota.
USER_COUNT_QUOTAS = {
    "operator-1": 20,
}


def get_permissions(role: str) -> dict:
    """Return full permission dict for a role, or all-False if unknown."""
    if role in ROLES:
        return ROLES[role].copy()
    return {key: False for key in ROLES.get("user", {})}


def has_permission(role: str, permission: str) -> bool:
    """Check whether a single permission is True for a given role."""
    return ROLES.get(role, {}).get(permission, False)


def get_user_count_quota(username: str) -> int | None:
    """Return per-session qualified-count quota for a username, if configured."""
    value = USER_COUNT_QUOTAS.get(username)
    if value is None:
        return None
    try:
        quota = int(value)
    except (TypeError, ValueError):
        return None
    return quota if quota > 0 else None
