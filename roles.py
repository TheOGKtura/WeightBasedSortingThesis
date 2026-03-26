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
    },
    "user": {
        "pushButton_start":     True,
        "pushButton_analytics": True,
        "pushButton_3":         False,
        "pushButton_home":      True,
        "pushButton_settings":  False,
    },
}

# ── User Accounts ──
USERS = {
    "admin": {
        "password": "123",
        "role":     "admin",
    },
    "user": {
        "password": "user123",
        "role":     "user",
    },
}


def get_permissions(role: str) -> dict:
    """Return full permission dict for a role, or all-False if unknown."""
    if role in ROLES:
        return ROLES[role].copy()
    return {key: False for key in ROLES.get("user", {})}


def has_permission(role: str, permission: str) -> bool:
    """Check whether a single permission is True for a given role."""
    return ROLES.get(role, {}).get(permission, False)
