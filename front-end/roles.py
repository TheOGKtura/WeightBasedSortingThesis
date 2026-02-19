# roles.py

ROLES = {
    "user": {
        "label": "User",
        "pin": "1234",
        "permissions": {
            "settings": False,
            "analytics": False,
            "logistics": True,
            "start": True
        }
    },
    "admin": {
        "label": "Admin",
        "pin": "9999",
        "permissions": {
            "settings": True,
            "analytics": True,
            "logistics": True,
            "start": True
        }
    }
}
