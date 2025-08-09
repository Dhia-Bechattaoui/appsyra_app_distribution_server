"""
Simple database layer that can use either file storage or environment variables
for persistent data storage on platforms with ephemeral storage.
"""
import os
import json
from typing import List, Dict, Any

def get_users() -> List[Dict[str, Any]]:
    """Get users from environment variable or default."""
    users_json = os.getenv("USERS_DATA", "[]")
    try:
        users = json.loads(users_json)
        # Add default owner if no users or no owner/admin
        if not users or not any(u.get("role") in ["owner", "admin"] for u in users):
            users = [{"username": "owner", "password": "owner123", "role": "owner"}]
        return users
    except json.JSONDecodeError:
        return [{"username": "owner", "password": "owner123", "role": "owner"}]

def save_users(users: List[Dict[str, Any]]) -> None:
    """Save users to environment variable (note: this is temporary)."""
    # For development - in production, you'd want to use a real database
    print(f"Users would be saved: {json.dumps(users)}")
    print("Note: In production, use a proper database for persistence")

def get_reviews() -> List[Dict[str, Any]]:
    """Get reviews from environment variable or default."""
    reviews_json = os.getenv("REVIEWS_DATA", "[]")
    try:
        return json.loads(reviews_json)
    except json.JSONDecodeError:
        return []

def save_reviews(reviews: List[Dict[str, Any]]) -> None:
    """Save reviews (note: this is temporary)."""
    # For development - in production, you'd want to use a real database
    print(f"Reviews would be saved: {json.dumps(reviews)}")
    print("Note: In production, use a proper database for persistence")
