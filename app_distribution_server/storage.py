import json

from fs import errors, open_fs, path
from typing import Optional

from app_distribution_server.build_info import BuildInfo, LegacyAppInfo, Platform
from app_distribution_server.config import STORAGE_URL, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL, AWS_DEFAULT_REGION
from app_distribution_server.errors import NotFoundError
from app_distribution_server.logger import logger
from app_distribution_server import database
import os

PLIST_FILE_NAME = "info.plist"
BUILD_INFO_JSON_FILE_NAME = "build_info.json"
LEGACY_BUILD_INFO_JSON_FILE_NAME = "app_info.json"
INDEXES_DIRECTORY = "_indexes"


# Configure filesystem with R2/S3 credentials if needed
def get_filesystem():
    if STORAGE_URL.startswith("s3://") and AWS_ENDPOINT_URL:
        # Set environment variables for s3fs to use custom endpoint (R2)
        os.environ.setdefault("AWS_S3_ENDPOINT_URL", AWS_ENDPOINT_URL)
        if AWS_ACCESS_KEY_ID:
            os.environ.setdefault("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
        if AWS_SECRET_ACCESS_KEY:
            os.environ.setdefault("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
        if AWS_DEFAULT_REGION:
            os.environ.setdefault("AWS_DEFAULT_REGION", AWS_DEFAULT_REGION)
        
        logger.info(f"Initializing S3 filesystem with endpoint: {AWS_ENDPOINT_URL}")
    
    return open_fs(STORAGE_URL, create=True)

filesystem = get_filesystem()


def create_parent_directories(upload_id: str):
    filesystem.makedirs(upload_id, recreate=True)


async def find_existing_upload(bundle_id: str, version_code: Optional[int] = None, build_number: Optional[str] = None) -> Optional[str]:
    # Try database first
    try:
        apps = await database.list_all_apps()
        for app in apps:
            if app['bundle_id'] == bundle_id:
                if version_code is not None and app.get('version_code') == version_code:
                    return app['upload_id']
                if build_number is not None and app.get('build_number') == build_number:
                    return app['upload_id']
    except Exception as e:
        logger.warning(f"Database query failed, falling back to filesystem: {e}")
    
    # Fallback to filesystem
    for upload_id in filesystem.listdir("."):
        try:
            build_info = await load_build_info(upload_id)
            if build_info.bundle_id == bundle_id:
                if version_code is not None and hasattr(build_info, 'version_code') and build_info.version_code == version_code:
                    return upload_id
                if build_number is not None and hasattr(build_info, 'build_number') and build_info.build_number == build_number:
                    return upload_id
        except Exception:
            continue
    return None


async def save_upload(build_info: BuildInfo, app_file_content: bytes):
    # Remove old build with same version_code/build_number if exists
    existing_upload_id = None
    if build_info.platform == Platform.android and build_info.version_code is not None:
        existing_upload_id = await find_existing_upload(build_info.bundle_id, version_code=build_info.version_code)
    elif build_info.platform == Platform.ios and build_info.build_number is not None:
        existing_upload_id = await find_existing_upload(build_info.bundle_id, build_number=build_info.build_number)
    if existing_upload_id:
        await delete_upload(existing_upload_id)
    
    create_parent_directories(build_info.upload_id)
    save_build_info(build_info)
    save_app_file(build_info, app_file_content)
    await set_latest_build(build_info)
    
    # Also save to database for persistence
    try:
        file_url = f"/api/uploads/{build_info.upload_id}/{build_info.platform.app_file_name}"
        await database.save_app_metadata(
            upload_id=build_info.upload_id,
            app_title=build_info.app_title,
            bundle_id=build_info.bundle_id,
            bundle_version=build_info.bundle_version,
            platform=build_info.platform.value,
            file_size=build_info.file_size,
            file_url=file_url,
            version_code=getattr(build_info, 'version_code', None),
            build_number=getattr(build_info, 'build_number', None)
        )
        logger.info(f"App metadata saved to database for upload {build_info.upload_id}")
    except Exception as e:
        logger.error(f"Failed to save app metadata to database: {e}")
        # Continue without failing the upload


def get_upload_platform(upload_id: str) -> Optional[Platform]:
    for platform in Platform:
        if filesystem.exists(path.join(upload_id, platform.app_file_name)):
            return platform

    return None


def get_upload_asserted_platform(
    upload_id: str,
    expected_platform: Optional[Platform] = None,
) -> Platform:
    upload_platform = get_upload_platform(upload_id)

    if upload_platform is None:
        raise NotFoundError()

    if expected_platform is None:
        return upload_platform

    if upload_platform == expected_platform:
        return upload_platform

    raise NotFoundError()


def save_build_info(build_info: BuildInfo):
    upload_id = build_info.upload_id
    filepath = f"{upload_id}/{BUILD_INFO_JSON_FILE_NAME}"

    with filesystem.open(filepath, "w") as app_info_file:
        app_info_file.write(
            build_info.model_dump_json(indent=2),
        )


async def load_build_info(upload_id: str, expected_platform: Optional[Platform] = None) -> BuildInfo:
    # First try to get from database
    try:
        app_metadata = await database.get_app_metadata(upload_id)
        if app_metadata:
            logger.info(f"Loaded app metadata from database for upload {upload_id}")
            return BuildInfo(
                upload_id=upload_id,
                app_title=app_metadata.get("app_title", "Unknown App"),
                bundle_id=app_metadata.get("bundle_id", "unknown"),
                bundle_version=app_metadata.get("bundle_version", "1.0"),
                version_code=app_metadata.get("version_code", 1),
                build_number=app_metadata.get("build_number", 1),
                platform=Platform(app_metadata.get("platform", "android")),
                file_size=app_metadata.get("file_size", 0),
                created_at=app_metadata.get("created_at")
            )
    except Exception as e:
        logger.warning(f"Failed to load app metadata from database: {e}")
    
    # Fall back to file system
    try:
        filepath = path.join(upload_id, BUILD_INFO_JSON_FILE_NAME)
        with filesystem.open(filepath, "r") as app_info_file:
            build_info_json = json.load(app_info_file)
            return BuildInfo.model_validate(build_info_json)

    except errors.ResourceNotFound:
        try:
            return migrate_legacy_app_info(upload_id)
        except Exception as e:
            logger.error(f"Failed to load build info for {upload_id}: {e}")
            # Return a minimal build info if everything fails
            return BuildInfo(
                upload_id=upload_id,
                app_title="Unknown App",
                bundle_id="unknown",
                bundle_version="1.0",
                version_code=1,
                build_number=1,
                platform=Platform.ANDROID,
                file_size=0,
                created_at=None
            )


def migrate_legacy_app_info(upload_id: str) -> BuildInfo:
    logger.info(f"Migrating legacy upload {upload_id!r} to v2")

    filepath = path.join(upload_id, LEGACY_BUILD_INFO_JSON_FILE_NAME)
    with filesystem.open(filepath, "r") as app_info_file:
        legacy_info_json = json.load(app_info_file)
        legacy_app_info = LegacyAppInfo.model_validate(legacy_info_json)

    file_size = filesystem.getsize(
        path.join(upload_id, Platform.ios.app_file_name),
    )

    build_info = BuildInfo(
        app_title=legacy_app_info.app_title,
        bundle_id=legacy_app_info.bundle_id,
        bundle_version=legacy_app_info.bundle_version,
        upload_id=upload_id,
        file_size=file_size,
        created_at=None,
        platform=Platform.ios,
    )

    save_build_info(build_info)
    logger.info(f"Successfully migrated legacy upload {upload_id!r} to v2")

    return build_info


def get_app_file_path(
    build_info: BuildInfo,
):
    return path.join(
        build_info.upload_id,
        build_info.platform.app_file_name,
    )


def save_app_file(
    build_info: BuildInfo,
    app_file: bytes,
):
    with filesystem.open(get_app_file_path(build_info), "wb+") as writable_app_file:
        writable_app_file.write(app_file)


def load_app_file(
    build_info: BuildInfo,
) -> bytes:
    with filesystem.open(get_app_file_path(build_info), "rb") as app_file:
        return app_file.read()


async def delete_upload(upload_id: str):
    try:
        # Delete from database
        await database.delete_app_metadata(upload_id)
        logger.info(f"App metadata deleted from database for upload {upload_id!r}")
    except Exception as e:
        logger.warning(f"Failed to delete app metadata from database: {e}")
    
    try:
        # Delete from filesystem
        if filesystem.exists(upload_id):
            filesystem.removetree(upload_id)
            logger.info(f"Upload directory {upload_id!r} deleted successfully")
        else:
            logger.info(f"Upload directory {upload_id!r} does not exist (already deleted or lost)")
    except Exception as e:
        logger.warning(f"Failed to delete upload directory {upload_id!r}: {e}")
        # Don't raise - allow the upload to continue even if file deletion fails


def get_latest_upload_by_bundle_id_filepath(bundle_id):
    return path.join(INDEXES_DIRECTORY, "latest_upload_by_bundle_id", f"{bundle_id}.txt")


async def set_latest_build(build_info: BuildInfo):
    # Still save to filesystem for compatibility
    filepath = get_latest_upload_by_bundle_id_filepath(build_info.bundle_id)
    filesystem.makedirs(path.dirname(filepath), recreate=True)

    with filesystem.open(filepath, "w") as file:
        file.write(build_info.upload_id)
    
    # Database already has this info via save_app_metadata, so no additional action needed


def get_latest_upload_id_by_bundle_id(bundle_id: str) -> Optional[str]:
    filepath = get_latest_upload_by_bundle_id_filepath(bundle_id)

    logger.info(f"Retrieving latest upload id from bundle {bundle_id!r} ({filepath!r})")

    if not filesystem.exists(filepath):
        return None

    with filesystem.open(filepath, "r") as file:
        return file.readline().strip()


async def list_builds_by_bundle_id(bundle_id: str):
    """Return a list of BuildInfo objects for all uploads with the given bundle_id, sorted by created_at descending."""
    builds = []
    
    # Try database first
    try:
        apps = await database.list_all_apps()
        for app in apps:
            if app['bundle_id'] == bundle_id:
                # Convert database record to BuildInfo-like object
                try:
                    build_info = await load_build_info(app['upload_id'])
                    builds.append(build_info)
                except Exception:
                    # If file doesn't exist, create BuildInfo from database data
                    from app_distribution_server.build_info import Platform
                    platform = Platform(app['platform']) if app['platform'] else Platform.ios
                    build_info = BuildInfo(
                        upload_id=app['upload_id'],
                        app_title=app['app_title'],
                        bundle_id=app['bundle_id'],
                        bundle_version=app['bundle_version'],
                        platform=platform,
                        file_size=app['file_size'],
                        created_at=app['created_at'].timestamp() if app.get('created_at') else None,
                        version_code=app.get('version_code'),
                        build_number=app.get('build_number')
                    )
                    builds.append(build_info)
        if builds:
            builds.sort(key=lambda b: b.created_at or 0, reverse=True)
            return builds
    except Exception as e:
        logger.warning(f"Database query failed, falling back to filesystem: {e}")
    
    # Fallback to filesystem
    for upload_id in filesystem.listdir("."):
        try:
            build_info = await load_build_info(upload_id)
            if build_info.bundle_id == bundle_id:
                builds.append(build_info)
        except Exception:
            continue
    builds.sort(key=lambda b: b.created_at or 0, reverse=True)
    return builds
