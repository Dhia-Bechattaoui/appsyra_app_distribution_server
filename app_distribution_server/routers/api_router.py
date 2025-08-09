import secrets

from fastapi import APIRouter, Depends, File, Path, UploadFile, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.security import APIKeyHeader

from app_distribution_server.build_info import (
    BuildInfo,
    Platform,
    get_build_info,
)
from app_distribution_server.config import (
    UPLOADS_SECRET_AUTH_TOKEN,
    get_absolute_url,
)
from app_distribution_server.errors import (
    InvalidFileTypeError,
    NotFoundError,
    UnauthorizedError,
)
from app_distribution_server.logger import logger
from app_distribution_server.storage import (
    delete_upload,
    get_latest_upload_id_by_bundle_id,
    get_upload_asserted_platform,
    load_build_info,
    save_upload,
)
import os
import json
import datetime
from collections import defaultdict
from app_distribution_server.routers.html_router import load_reviews, get_current_user

x_auth_token_dependency = APIKeyHeader(name="X-Auth-Token")


def x_auth_token_validator(
    x_auth_token: str = Depends(x_auth_token_dependency),
):
    if not secrets.compare_digest(x_auth_token, UPLOADS_SECRET_AUTH_TOKEN):
        raise UnauthorizedError()


router = APIRouter(
    tags=["API"],
    dependencies=[Depends(x_auth_token_validator)],
)


async def _upload_app(
    app_file: UploadFile,
) -> BuildInfo:
    platform: Platform

    if app_file.filename is None:
        raise InvalidFileTypeError()

    if app_file.filename.endswith(".ipa"):
        platform = Platform.ios

    elif app_file.filename.endswith(".apk"):
        platform = Platform.android

    else:
        raise InvalidFileTypeError()

    app_file_content = app_file.file.read()

    build_info = get_build_info(platform, app_file_content)
    upload_id = build_info.upload_id

    logger.debug(f"Starting upload of {upload_id!r}")

    await save_upload(build_info, app_file_content)

    logger.info(f"Successfully uploaded {build_info.bundle_id!r} ({upload_id!r})")

    return build_info


_upload_route_kwargs = {
    "responses": {
        InvalidFileTypeError.STATUS_CODE: {
            "description": InvalidFileTypeError.ERROR_MESSAGE,
        },
        UnauthorizedError.STATUS_CODE: {
            "description": UnauthorizedError.ERROR_MESSAGE,
        },
    },
    "summary": "Upload an iOS/Android app Build",
    "description": "On swagger UI authenticate in the upper right corner ('Authorize' button).",
}


@router.post("/upload", **_upload_route_kwargs)
async def _plaintext_post_upload(
    app_file: UploadFile = File(description="An `.ipa` or `.apk` build"),
) -> PlainTextResponse:
    build_info = await _upload_app(app_file)

    return PlainTextResponse(
        content=get_absolute_url(f"/get/{build_info.upload_id}"),
    )


@router.post("/api/upload", **_upload_route_kwargs)
async def _json_api_post_upload(
    app_file: UploadFile = File(description="An `.ipa` or `.apk` build"),
) -> BuildInfo:
    return await _upload_app(app_file)


async def _api_delete_app_upload(
    upload_id: str = Path(),
) -> PlainTextResponse:
    get_upload_asserted_platform(upload_id)

    await delete_upload(upload_id)
    logger.info(f"Upload {upload_id!r} deleted successfully")

    return PlainTextResponse(status_code=200, content="Upload deleted successfully")


router.delete(
    "/api/delete/{upload_id}",
    summary="Delete an uploaded app build",
    response_class=PlainTextResponse,
)(_api_delete_app_upload)

router.delete(
    "/delete/{upload_id}",
    deprecated=True,
    summary="Delete an uploaded app build. Deprecated, use /api/delete/UPLOAD_ID instead",
    response_class=PlainTextResponse,
)(_api_delete_app_upload)


@router.get(
    "/api/bundle/{bundle_id}/latest_upload",
    summary="Retrieve the latest upload from a bundle ID",
)
async def api_get_latest_upload_by_bundle_id(
    bundle_id: str = Path(
        pattern=r"^[a-zA-Z0-9\.\-\_]{1,256}$",
    ),
) -> BuildInfo:
    upload_id = get_latest_upload_id_by_bundle_id(bundle_id)

    if not upload_id:
        raise NotFoundError()

    get_upload_asserted_platform(upload_id)
    return await load_build_info(upload_id)


# Move this endpoint outside the router with API key dependency
download_stats_router = APIRouter(tags=["Admin Stats"])

@download_stats_router.get("/admin/api/download-stats", response_class=JSONResponse)
async def download_stats(
    group_by: str = Query("day", enum=["day", "month", "year"]),
    bundle_id: str = Query(None)
):
    log_path = "logs/downloads.log"
    if not os.path.exists(log_path):
        return {"data": []}
    counts = defaultdict(int)
    with open(log_path, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if bundle_id and entry.get("bundle_id") != bundle_id:
                    continue
                ts = entry.get("timestamp")
                dt = datetime.datetime.fromisoformat(ts)
                if group_by == "day":
                    key = dt.strftime("%Y-%m-%d")
                elif group_by == "month":
                    key = dt.strftime("%Y-%m")
                else:
                    key = dt.strftime("%Y")
                counts[key] += 1
            except Exception:
                continue
    data = [{"period": k, "count": v} for k, v in sorted(counts.items())]
    return {"data": data}

@download_stats_router.get("/admin/api/activity", response_class=JSONResponse)
async def activity_feed(request: Request, limit: int = Query(10)):
    user = await get_current_user(request)
    if user.get("role") not in ["owner", "admin"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    import os
    lang = request.cookies.get("lang", "en")
    log_path = "logs/activity.log"
    if not os.path.exists(log_path):
        return {"data": []}
    lines = []
    with open(log_path, "r") as f:
        for line in f:
            try:
                lines.append(json.loads(line))
            except Exception:
                continue
    # Sort by timestamp descending
    lines = sorted(lines, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
    # Load translations
    try:
        with open(f"translations/{lang}.json", "r") as tf:
            translations = json.load(tf)
    except Exception:
        with open("translations/en.json", "r") as tf:
            translations = json.load(tf)
    messages = []
    for entry in lines:
        user = entry.get("username", "admin")
        if entry["type"] == "create_app":
            msg = translations["activity_created_app"].format(user=user, app=entry.get('app_title'), id=entry.get('bundle_id'))
        elif entry["type"] == "upload_version":
            msg = translations["activity_uploaded_version"].format(user=user, version=entry.get('version'), app=entry.get('app_title'))
        elif entry["type"] == "edit_app":
            msg = translations["activity_edited_app"].format(user=user, app=entry.get('app_title'), id=entry.get('bundle_id'))
        elif entry["type"] == "change_settings":
            msg = translations["activity_changed_settings"].format(user=user, policy=entry.get('policy'), old_policy=entry.get('old_policy', ''), lang=entry.get('lang', ''))
        elif entry["type"] == "reply_review":
            msg = translations["activity_reply_review"].format(admin=entry.get('admin'), review_user=entry.get('review_user'), bundle_id=entry.get('bundle_id'), reply=entry.get('reply'))
        else:
            msg = translations["activity_default"].format(user=user)
        messages.append({"timestamp": entry.get("timestamp"), "message": msg})
    return {"data": messages}

@download_stats_router.get("/admin/api/recent-reviews", response_class=JSONResponse)
async def recent_reviews(request: Request, limit: int = 20):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    reviews = await load_reviews()
    reviews = sorted(reviews, key=lambda r: r.get("timestamp", 0), reverse=True)[:limit]
    # Attach app info to each review
    for r in reviews:
        upload_id = get_latest_upload_id_by_bundle_id(r["bundle_id"])
        if upload_id:
            try:
                build = await load_build_info(upload_id)
                r["app_title"] = build.app_title
                r["app_picture_url"] = build.app_picture_url
                r["app_page_url"] = f"/app/{build.bundle_id}"
            except Exception:
                r["app_title"] = r["bundle_id"]
                r["app_picture_url"] = None
                r["app_page_url"] = f"/app/{r['bundle_id']}"
        else:
            r["app_title"] = r["bundle_id"]
            r["app_picture_url"] = None
            r["app_page_url"] = f"/app/{r['bundle_id']}"
    return {"reviews": reviews}

@download_stats_router.get("/admin/api/unique-downloads", response_class=JSONResponse)
async def unique_downloads(bundle_id: str):
    log_path = "logs/downloads.log"
    if not os.path.exists(log_path):
        return {"count": 0}
    unique_ips = set()
    with open(log_path, "r") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("bundle_id") == bundle_id:
                    unique_ips.add(entry.get("ip"))
            except Exception:
                continue
    return {"count": len(unique_ips)}

# At the end of the file, include this router in your FastAPI app
# app.include_router(download_stats_router)
