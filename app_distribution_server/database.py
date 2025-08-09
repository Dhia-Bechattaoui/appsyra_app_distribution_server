"""
Database layer using PostgreSQL for persistent storage.
"""
import os
import json
import asyncpg
from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db_connection():
    """Get database connection."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable not set")
    return await asyncpg.connect(DATABASE_URL)

async def init_database():
    """Initialize database tables."""
    try:
        conn = await get_db_connection()
    except ValueError as e:
        # Database URL not available, skip initialization
        print(f"Skipping database initialization: {e}")
        return
    
    try:
        # Create users table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Create reviews table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                app_name VARCHAR(255),
                reviewer_name VARCHAR(255),
                rating INTEGER,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Create apps table for app metadata
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS apps (
                id SERIAL PRIMARY KEY,
                upload_id VARCHAR(255) UNIQUE NOT NULL,
                app_title VARCHAR(255),
                bundle_id VARCHAR(255),
                bundle_version VARCHAR(255),
                version_code INTEGER,
                build_number VARCHAR(255),
                platform VARCHAR(20),
                file_size BIGINT,
                file_url VARCHAR(500),
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Create settings table
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(255) PRIMARY KEY,
                value JSONB,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Create default owner user if no users exist
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if user_count == 0:
            await conn.execute(
                "INSERT INTO users (username, password, role) VALUES ($1, $2, $3)",
                "owner", "owner123", "owner"
            )
            
    finally:
        await conn.close()

async def get_users() -> List[Dict[str, Any]]:
    """Get all users from database."""
    try:
        conn = await get_db_connection()
    except ValueError:
        # Database not available, return default user
        return [{"username": "owner", "password": "owner123", "role": "owner"}]
    
    try:
        rows = await conn.fetch("SELECT username, password, role FROM users")
        return [{"username": row["username"], "password": row["password"], "role": row["role"]} for row in rows]
    finally:
        await conn.close()

async def save_user(username: str, password: str, role: str) -> bool:
    """Add a new user to database."""
    conn = await get_db_connection()
    try:
        await conn.execute(
            "INSERT INTO users (username, password, role) VALUES ($1, $2, $3)",
            username, password, role
        )
        return True
    except asyncpg.UniqueViolationError:
        return False
    finally:
        await conn.close()

async def delete_user(username: str) -> bool:
    """Delete a user from database."""
    conn = await get_db_connection()
    try:
        result = await conn.execute("DELETE FROM users WHERE username = $1", username)
        return result.replace("DELETE ", "").strip() != "0"
    finally:
        await conn.close()

async def get_reviews() -> List[Dict[str, Any]]:
    """Get all reviews from database."""
    try:
        conn = await get_db_connection()
    except ValueError:
        # Database not available, return empty list
        return []
    
    try:
        rows = await conn.fetch(
            "SELECT app_name, reviewer_name, rating, comment, created_at FROM reviews ORDER BY created_at DESC"
        )
        return [
            {
                "app_name": row["app_name"],
                "reviewer_name": row["reviewer_name"], 
                "rating": row["rating"],
                "comment": row["comment"],
                "created_at": row["created_at"].isoformat()
            } 
            for row in rows
        ]
    finally:
        await conn.close()

async def save_review(app_name: str, reviewer_name: str, rating: int, comment: str) -> None:
    """Save a review to database."""
    conn = await get_db_connection()
    try:
        await conn.execute(
            "INSERT INTO reviews (app_name, reviewer_name, rating, comment) VALUES ($1, $2, $3, $4)",
            app_name, reviewer_name, rating, comment
        )
    finally:
        await conn.close()

# App metadata functions
async def save_app_metadata(upload_id: str, app_title: str, bundle_id: str, 
                           bundle_version: str, platform: str, file_size: int,
                           file_url: str, version_code: int = None, build_number: str = None) -> None:
    """Save app metadata to database."""
    conn = await get_db_connection()
    try:
        await conn.execute("""
            INSERT INTO apps (upload_id, app_title, bundle_id, bundle_version, 
                            version_code, build_number, platform, file_size, file_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (upload_id) DO UPDATE SET
                app_title = EXCLUDED.app_title,
                bundle_id = EXCLUDED.bundle_id,
                bundle_version = EXCLUDED.bundle_version,
                version_code = EXCLUDED.version_code,
                build_number = EXCLUDED.build_number,
                platform = EXCLUDED.platform,
                file_size = EXCLUDED.file_size,
                file_url = EXCLUDED.file_url
        """, upload_id, app_title, bundle_id, bundle_version, version_code, 
             build_number, platform, file_size, file_url)
    finally:
        await conn.close()

async def get_app_metadata(upload_id: str) -> dict:
    """Get app metadata from database."""
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM apps WHERE upload_id = $1", upload_id
        )
        if row:
            return dict(row)
        return None
    finally:
        await conn.close()

async def list_all_apps() -> List[Dict[str, Any]]:
    """Get all apps from database."""
    try:
        conn = await get_db_connection()
    except ValueError:
        # Database not available, return empty list
        return []
    
    try:
        rows = await conn.fetch(
            "SELECT * FROM apps ORDER BY created_at DESC"
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def delete_app_metadata(upload_id: str) -> bool:
    """Delete app metadata from database."""
    conn = await get_db_connection()
    try:
        result = await conn.execute("DELETE FROM apps WHERE upload_id = $1", upload_id)
        return result.replace("DELETE ", "").strip() != "0"
    finally:
        await conn.close()

# Settings functions
async def get_setting(key: str, default_value=None):
    """Get setting from database."""
    try:
        conn = await get_db_connection()
    except ValueError:
        # Database not available, return default
        return default_value
    
    try:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        if row:
            # Parse JSON string back to Python object
            try:
                return json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
            except (json.JSONDecodeError, TypeError):
                return row["value"]
        return default_value
    finally:
        await conn.close()

async def save_setting(key: str, value) -> None:
    """Save setting to database."""
    conn = await get_db_connection()
    try:
        await conn.execute("""
            INSERT INTO settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET 
                value = EXCLUDED.value,
                updated_at = NOW()
        """, key, json.dumps(value))
    finally:
        await conn.close()
