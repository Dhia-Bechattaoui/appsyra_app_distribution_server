from fastapi import APIRouter, Request, Response, Form, UploadFile
from fastapi import HTTPException as FastApiHTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import HTTP_303_SEE_OTHER
from starlette.responses import Response as StarletteResponse
import os
from app_distribution_server.config import LOGO_URL
from typing import Union
from app_distribution_server import database

from app_distribution_server.build_info import (
    Platform,
    BuildInfo,
    get_build_info,
)
from app_distribution_server.config import (
    APP_TITLE,
    LOGO_URL,
    get_absolute_url,
    COMPANY_NAME,
)
from app_distribution_server.qrcode import get_qr_code_svg
from app_distribution_server.storage import (
    get_upload_asserted_platform,
    load_build_info,
    list_builds_by_bundle_id,
    save_build_info,
    save_upload,
)
import shutil
import json
import datetime
import time
async def get_settings():
    """Get settings from database."""
    try:
        return await database.get_setting("app_settings", {"duplicate_upload_policy": "error"})
    except Exception as e:
        print(f"Error loading settings from database: {e}")
        return {"duplicate_upload_policy": "error"}

async def save_settings(settings):
    """Save settings to database."""
    try:
        await database.save_setting("app_settings", settings)
    except Exception as e:
        print(f"Error saving settings to database: {e}")

async def load_users():
    """Load users from database."""
    try:
        return await database.get_users()
    except Exception as e:
        print(f"Error loading users from database: {e}")
        # Fallback to default user
        return [{"username": "owner", "password": "owner123", "role": "owner"}]

async def save_users(users):
    """Save users to database (individual users should be saved via database.save_user)."""
    # This is kept for compatibility but individual users should be saved via database.save_user
    print("Note: Use database.save_user() for adding individual users")

async def load_reviews():
    """Load reviews from database."""
    try:
        return await database.get_reviews()
    except Exception as e:
        print(f"Error loading reviews from database: {e}")
        return []

async def save_reviews(reviews):
    """Save reviews to database (individual reviews should be saved via database.save_review)."""
    # This is kept for compatibility but individual reviews should be saved via database.save_review
    print("Note: Use database.save_review() for adding individual reviews")

async def get_current_user(request):
    username = request.cookies.get("username")
    admin_auth = request.cookies.get("admin_auth")
    if not username or admin_auth != "1":
        return {"username": None, "role": "user"}
    users = await load_users()
    for u in users:
        if u["username"] == username:
            return u
    return {"username": username, "role": "user"}

router = APIRouter(tags=["HTML page handling"])

templates = Jinja2Templates(directory="templates")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"  # Change this in production!

@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    user = await get_current_user(request)
    if user["username"] and user["role"] in ["owner", "admin"]:
        return RedirectResponse("/admin", status_code=HTTP_303_SEE_OTHER)
    if user["username"] and user["role"] == "user":
        return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "login.jinja.html",
        {"request": request, "error": None, "is_logged_in": False, "current_user_role": user["role"], "tr": tr, "lang": lang, "translations": translations, "logo_url": LOGO_URL}
    )

@router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    users = await load_users()
    user = next((u for u in users if u["username"] == username and u["password"] == password), None)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    if user:
        response = RedirectResponse(url="/admin", status_code=HTTP_303_SEE_OTHER)
        response.set_cookie("admin_auth", "1", httponly=True, max_age=86400)
        response.set_cookie("username", username, max_age=86400)
        return response
    return templates.TemplateResponse(
        "login.jinja.html",
        {"request": request, "error": "Invalid username or password.", "tr": tr, "lang": lang, "translations": translations, "logo_url": LOGO_URL}
    )

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "admin-dashboard.jinja.html",
        {
            "request": request,
            "lang": lang,
            "tr": tr,
            "active_menu": "dashboard",
            "translations": translations,
            "company_name": COMPANY_NAME,
        }
    )

@router.get("/logout")
async def admin_logout():
    response = RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    response.delete_cookie("admin_auth")
    response.delete_cookie("username")
    return response

@router.get("/admin/apps", response_class=HTMLResponse)
async def admin_apps(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    from app_distribution_server.storage import load_build_info
    from fs import errors
    apps = {}
    for upload_id in list_builds_by_bundle_id.__globals__["filesystem"].listdir("."):
        try:
            build_info = await load_build_info(upload_id)
            if build_info.bundle_id not in apps:
                apps[build_info.bundle_id] = build_info
        except errors.ResourceNotFound:
            continue
        except Exception:
            continue
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "admin-apps.jinja.html",
        {"request": request, "apps": list(apps.values()), "lang": lang, "tr": tr, "active_menu": "apps"}
    )

@router.get("/admin/apps/create", response_class=HTMLResponse)
async def admin_create_app_get(request: Request):
    if request.cookies.get("admin_auth") != "1":
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse("admin-create-app.jinja.html", {"request": request, "error": None, "tr": tr, "lang": lang, "translations": translations})

@router.post("/admin/apps/create", response_class=HTMLResponse)
async def admin_create_app_post(request: Request, app_title: str = Form(...), bundle_id: str = Form(...), app_description: str = Form(None), app_picture_url: str = Form(None)):
    if request.cookies.get("admin_auth") != "1":
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    # Check if app already exists
    builds = await list_builds_by_bundle_id(bundle_id)
    if builds:
        return templates.TemplateResponse("admin-create-app.jinja.html", {"request": request, "error": "App with this Bundle ID already exists.", "tr": tr, "lang": lang, "translations": translations})
    # Create a dummy BuildInfo entry (no version yet)
    dummy_build = BuildInfo(
        upload_id=f"dummy-{bundle_id}",
        platform=Platform.ios,  # Default, can be updated later
        app_title=app_title,
        bundle_id=bundle_id,
        bundle_version="-",
        created_at=None,
        file_size=0,
        app_description=app_description,
        app_picture_url=app_picture_url,
    )
    save_build_info(dummy_build)
    # Log activity
    username = request.cookies.get("username", "admin")
    activity = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "type": "create_app",
        "bundle_id": bundle_id,
        "app_title": app_title,
        "username": username
    }
    with open(os.path.join("logs", "activity.log"), "a") as f:
        f.write(json.dumps(activity) + "\n")
    return RedirectResponse("/admin/apps", status_code=HTTP_303_SEE_OTHER)

@router.get("/admin/apps/{bundle_id}/edit", response_class=HTMLResponse)
async def admin_edit_app_get(request: Request, bundle_id: str):
    if request.cookies.get("admin_auth") != "1":
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    builds = await list_builds_by_bundle_id(bundle_id)
    if not builds:
        raise FastApiHTTPException(status_code=404, detail="App not found")
    app_info = builds[0]
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse("admin-edit-app.jinja.html", {"request": request, "app_info": app_info, "bundle_id": bundle_id, "error": None, "tr": tr, "lang": lang, "translations": translations})

@router.post("/admin/apps/{bundle_id}/edit", response_class=HTMLResponse)
async def admin_edit_app_post(request: Request, bundle_id: str, app_title: str = Form(...), app_description: str = Form(None), app_picture_url: str = Form(None), app_picture_file: UploadFile = None):
    if request.cookies.get("admin_auth") != "1":
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    builds = await list_builds_by_bundle_id(bundle_id)
    if not builds:
        raise FastApiHTTPException(status_code=404, detail="App not found")
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    # Handle image upload
    if app_picture_file and app_picture_file.filename:
        ext = app_picture_file.filename.split('.')[-1].lower()
        if ext not in ["jpg", "jpeg", "png", "webp", "gif"]:
            return templates.TemplateResponse("admin-edit-app.jinja.html", {"request": request, "app_info": builds[0], "bundle_id": bundle_id, "error": "Invalid image format.", "tr": tr, "lang": lang, "translations": translations})
        photo_dir = os.path.join("static", "app_photos")
        os.makedirs(photo_dir, exist_ok=True)
        photo_path = os.path.join(photo_dir, f"{bundle_id}.{ext}")
        with open(photo_path, "wb") as f:
            shutil.copyfileobj(app_picture_file.file, f)
        app_picture_url = f"/static/app_photos/{bundle_id}.{ext}"
    # Update all builds for this app with new metadata
    for build in builds:
        build.app_title = app_title
        build.app_description = app_description
        build.app_picture_url = app_picture_url
        save_build_info(build)
    # Log activity
    username = request.cookies.get("username", "admin")
    activity = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "type": "edit_app",
        "bundle_id": bundle_id,
        "app_title": app_title,
        "username": username
    }
    with open(os.path.join("logs", "activity.log"), "a") as f:
        f.write(json.dumps(activity) + "\n")
    return RedirectResponse(f"/admin/apps", status_code=HTTP_303_SEE_OTHER)

@router.get("/admin/new-app/upload", response_class=HTMLResponse)
async def admin_upload_version_get(request: Request):
    if request.cookies.get("admin_auth") != "1":
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse("admin-upload-version-new.jinja.html", {"request": request, "error": None, "tr": tr, "lang": lang, "translations": translations})

@router.post("/admin/new-app/upload", response_class=HTMLResponse)
async def admin_upload_version_post(request: Request, app_file: UploadFile = Form(...)):
    if request.cookies.get("admin_auth") != "1":
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    file_bytes = await app_file.read()
    filename = app_file.filename or ""
    if filename.endswith(".ipa"):
        platform = Platform.ios
    elif filename.endswith(".apk"):
        platform = Platform.android
    else:
        return templates.TemplateResponse("admin-upload-version-new.jinja.html", {"request": request, "error": "Invalid file type. Only .ipa and .apk are supported.", "tr": tr, "lang": lang, "translations": translations})
    build_info = get_build_info(platform, file_bytes)
    # Duplicate version check
    settings = await get_settings()
    policy = settings.get("duplicate_upload_policy", "replace")
    builds = await list_builds_by_bundle_id(build_info.bundle_id)
    for b in builds:
        if b.bundle_version == build_info.bundle_version:
            if policy == "error":
                return templates.TemplateResponse("admin-upload-version-new.jinja.html", {"request": request, "error": f"A version with this version code ({build_info.bundle_version}) already exists for this app.", "tr": tr, "lang": lang, "translations": translations})
            # If replace, break and allow overwrite
            break
    await save_upload(build_info, file_bytes)
    # Log activity
    username = request.cookies.get("username", "admin")
    activity = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "type": "upload_version",
        "bundle_id": build_info.bundle_id,
        "app_title": build_info.app_title,
        "version": build_info.bundle_version,
        "username": username
    }
    with open(os.path.join("logs", "activity.log"), "a") as f:
        f.write(json.dumps(activity) + "\n")
    return RedirectResponse(f"/app/{build_info.bundle_id}", status_code=HTTP_303_SEE_OTHER)


@router.get("/get/{upload_id}/qrcode")
async def get_qrcode_image(request: Request, upload_id: str):
    build_info = await load_build_info(upload_id)
    
    # Get the base URL from the request to ensure it matches the current domain
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    
    if build_info.platform == Platform.ios:
        plist_url = f"{base_url}/get/{upload_id}/app.plist"
        install_url = f"itms-services://?action=download-manifest&url={plist_url}"
    else:
        install_url = f"{base_url}/get/{upload_id}/app.apk"
    
    svg = get_qr_code_svg(install_url)
    return Response(content=svg, media_type="image/svg+xml")


@router.get(
    "/app/{bundle_id}",
    response_class=HTMLResponse,
    summary="Show app info, latest version, and archive of previous versions",
)
async def app_overview_page(request: Request, bundle_id: str) -> HTMLResponse:
    builds = await list_builds_by_bundle_id(bundle_id)
    # Sort by version_code (descending), fallback to created_at if version_code is None
    def build_sort_key(b):
        return (b.version_code if b.version_code is not None else 0, b.created_at or 0)
    builds = sorted(builds, key=build_sort_key, reverse=True)
    if not builds:
        raise FastApiHTTPException(status_code=404, detail="App not found")
    latest = builds[0]
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    # Calculate reviews_count and avg_rating
    all_reviews = await load_reviews()
    app_reviews = [r for r in all_reviews if r["bundle_id"] == bundle_id]
    reviews_count = len(app_reviews)
    avg_rating = round(sum(r.get("rating", 0) for r in app_reviews) / reviews_count, 1) if reviews_count else 0
    # Calculate downloads_count
    downloads_count = 0
    log_path = os.path.join("logs", "downloads.log")
    if os.path.exists(log_path):
        with open(log_path, "r") as f:
            downloads_count = len([1 for line in f if json.loads(line).get("bundle_id") == bundle_id])
    return templates.TemplateResponse(
        request=request,
        name="app-overview.jinja.html",
        context={
            "page_title": f"{latest.app_title} - App Overview",
            "app_info": latest,
            "builds": builds,
            "logo_url": LOGO_URL,
            "lang": lang,
            "tr": tr,
            "company_name": COMPANY_NAME,
            "translations": translations,
            "avg_rating": avg_rating,
            "reviews_count": reviews_count,
            "downloads_count": downloads_count,
        },
    )

@router.get("/app/{bundle_id}/{upload_id}", response_class=HTMLResponse)
async def app_version_page(request: Request, bundle_id: str, upload_id: str) -> HTMLResponse:
    builds = await list_builds_by_bundle_id(bundle_id)
    def build_sort_key(b):
        return (b.version_code if b.version_code is not None else 0, b.created_at or 0)
    builds = sorted(builds, key=build_sort_key, reverse=True)
    build = next((b for b in builds if b.upload_id == upload_id), None)
    if not build:
        raise FastApiHTTPException(status_code=404, detail="Version not found")
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        request=request,
        name="app-version.jinja.html",
        context={
            "page_title": f"{build.app_title} @{build.bundle_version} - App Version",
            "app_info": build,
            "builds": builds,
            "logo_url": LOGO_URL,
            "lang": lang,
            "tr": tr,
            "translations": translations,
        },
    )

@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_get(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    settings = await get_settings()
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "admin-settings.jinja.html",
        {"request": request, "policy": settings.get("duplicate_upload_policy", "replace"), "message": None, "lang": lang, "tr": tr, "active_menu": "settings"}
    )

@router.post("/admin/settings", response_class=HTMLResponse)
async def admin_settings_post(request: Request, duplicate_upload_policy: str = Form(...), lang: str = Form(None)):
    settings = await get_settings()
    old_policy = settings.get("duplicate_upload_policy")
    settings["duplicate_upload_policy"] = duplicate_upload_policy
    await save_settings(settings)
    # Log activity if policy changed
    if duplicate_upload_policy != old_policy:
        username = request.cookies.get("username", "admin")
        activity = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "type": "change_settings",
            "policy": duplicate_upload_policy,
            "old_policy": old_policy,
            "lang": lang,
            "username": username
        }
        with open(os.path.join("logs", "activity.log"), "a") as f:
            f.write(json.dumps(activity) + "\n")
    # Set language cookie if changed
    response = templates.TemplateResponse(
        "admin-settings.jinja.html",
        {
            "request": request,
            "policy": duplicate_upload_policy,
            "message": "Settings saved.",
            "lang": lang or get_lang(request),
            "tr": (lambda key: load_translations(lang or get_lang(request)).get(key, key))
        }
    )
    if lang:
        response.set_cookie("lang", lang, max_age=60*60*24*365)
    return response

@router.post("/set-lang")
async def set_lang(request: Request, lang: str = Form(...)):
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    response.set_cookie("lang", lang, max_age=60*60*24*365)
    return response

# Helper to get lang from cookie

def get_lang(request: Request):
    cookie_lang = request.cookies.get("lang")
    if cookie_lang:
        return cookie_lang
    accept_lang = request.headers.get("accept-language", "").lower()
    if accept_lang.startswith("ar") or ",ar" in accept_lang:
        return "ar"
    return "en"

def load_translations(lang):
    try:
        with open(os.path.join("translations", f"{lang}.json"), "r") as f:
            return json.load(f)
    except Exception:
        with open(os.path.join("translations", "en.json"), "r") as f:
            return json.load(f)

# Patch all template responses to include lang
from functools import wraps

def with_lang(template_func):
    @wraps(template_func)
    async def wrapper(*args, **kwargs):
        request = kwargs.get("request") or (args[0] if args else None)
        lang = get_lang(request) if request else "en"
        resp = await template_func(*args, **kwargs)
        if hasattr(resp, "template") and hasattr(resp, "context"):
            resp.context["lang"] = lang
        return resp
    return wrapper

# Patch all GET routes that render templates
# router.routes = [
#     (r if not hasattr(r.endpoint, "__name__") or not r.endpoint.__name__.startswith("admin_settings_")
#      else r.__class__(r.path, with_lang(r.endpoint), **{k: v for k, v in r.__dict__.items() if k != "endpoint"}))
#     for r in router.routes
# ]


async def render_error_page(
    request: Request,
    user_error: Union[FastApiHTTPException, StarletteHTTPException],
) -> Response:
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        request=request,
        status_code=user_error.status_code,
        name="error.jinja.html",
        context={
            "page_title": user_error.detail,
            "error_message": f"{user_error.status_code} - {user_error.detail}",
            "lang": lang,
            "tr": tr,
        },
    )

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "home.jinja.html",
        {"request": request, "logo_url": LOGO_URL, "lang": lang, "tr": tr, "page_title": APP_TITLE}
    )

@router.get("/apps", response_class=HTMLResponse)
async def public_apps(request: Request):
    from app_distribution_server.storage import load_build_info
    from fs import errors
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    apps = {}
    for upload_id in list_builds_by_bundle_id.__globals__["filesystem"].listdir("."):
        try:
            build_info = await load_build_info(upload_id)
            if build_info.bundle_id not in apps:
                apps[build_info.bundle_id] = build_info
        except errors.ResourceNotFound:
            continue
        except Exception:
            continue
    return templates.TemplateResponse(
        "apps.jinja.html",
        {"request": request, "apps": list(apps.values()), "lang": lang, "tr": tr, "logo_url": LOGO_URL, "page_title": f"Apps - {APP_TITLE}"}
    )

@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "about.jinja.html",
        {"request": request, "lang": lang, "tr": tr, "logo_url": LOGO_URL, "page_title": f"About - {APP_TITLE}"}
    )

@router.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request):
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "contact.jinja.html",
        {"request": request, "lang": lang, "tr": tr, "logo_url": LOGO_URL, "page_title": f"Contact - {APP_TITLE}"}
    )

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return RedirectResponse("/", status_code=HTTP_303_SEE_OTHER)
    lang = get_lang(request)
    translations = load_translations(lang)
    def tr(key):
        return translations.get(key, key)
    return templates.TemplateResponse(
        "admin-users.jinja.html",
        {"request": request, "lang": lang, "tr": tr, "active_menu": "users", "current_user_role": user["role"]}
    )

@router.get("/admin/api/users")
async def api_list_users(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return {"error": "forbidden"}
    users = await load_users()
    return {"users": [{"username": u["username"], "role": u["role"]} for u in users]}

@router.post("/admin/api/users/create")
async def api_create_user(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return {"error": "forbidden"}
    data = await request.json()
    users = await load_users()
    if any(u["username"] == data["username"] for u in users):
        return {"error": "exists"}
    if data["role"] == "admin" and user["role"] != "owner":
        return {"error": "forbidden"}
    users.append({"username": data["username"], "password": data["password"], "role": data["role"]})
    await save_users(users)
    return {"ok": True}

@router.post("/admin/api/users/delete")
async def api_delete_user(request: Request):
    user = await get_current_user(request)
    data = await request.json()
    users = await load_users()
    target = next((u for u in users if u["username"] == data["username"]), None)
    if not target:
        return {"error": "notfound"}
    if target["role"] == "owner":
        return {"error": "forbidden"}
    if target["role"] == "admin" and user["role"] != "owner":
        return {"error": "forbidden"}
    users = [u for u in users if u["username"] != data["username"]]
    await save_users(users)
    return {"ok": True}

@router.post("/admin/api/users/role")
async def api_change_role(request: Request):
    user = await get_current_user(request)
    data = await request.json()
    users = await load_users()
    target = next((u for u in users if u["username"] == data["username"]), None)
    if not target:
        return {"error": "notfound"}
    if target["role"] == "owner":
        return {"error": "forbidden"}
    if data["role"] == "admin" and user["role"] != "owner":
        return {"error": "forbidden"}
    # Only owner can promote to owner
    if data["role"] == "owner" and user["role"] != "owner":
        return {"error": "forbidden"}
    # If switching to owner, demote current owner
    if data["role"] == "owner":
        for u in users:
            if u["role"] == "owner":
                u["role"] = "admin"
        target["role"] = "owner"
    else:
        target["role"] = data["role"]
    await save_users(users)
    return {"ok": True}

@router.post("/admin/api/users/update")
async def api_update_user(request: Request):
    user = await get_current_user(request)
    data = await request.json()
    users = await load_users()
    target = next((u for u in users if u["username"] == data["old_username"]), None)
    if not target:
        return {"error": "notfound"}
    if target["role"] == "owner":
        return {"error": "forbidden"}
    if target["role"] == "admin" and user["role"] != "owner":
        return {"error": "forbidden"}
    # Prevent duplicate usernames
    if data["username"] != data["old_username"] and any(u["username"] == data["username"] for u in users):
        return {"error": "exists"}
    target["username"] = data["username"]
    if data.get("password"):
        target["password"] = data["password"]
    await save_users(users)
    return {"ok": True}

@router.get("/api/reviews/app/{bundle_id}")
async def api_get_app_reviews(bundle_id: str, request: Request):
    reviews = await load_reviews()
    user = await get_current_user(request)
    user_review = None
    if user["username"]:
        for r in reviews:
            if r["bundle_id"] == bundle_id and r["username"] == user["username"]:
                user_review = r
                break
    return {"reviews": [r for r in reviews if r["bundle_id"] == bundle_id], "user_review": user_review}

@router.get("/api/reviews/version/{bundle_id}/{upload_id}")
async def api_get_version_reviews(bundle_id: str, upload_id: str):
    reviews = await load_reviews()
    return {"reviews": [r for r in reviews if r["bundle_id"] == bundle_id and r.get("upload_id") == upload_id]}

@router.post("/api/reviews/add")
async def api_add_review(request: Request):
    user = await get_current_user(request)
    if not user["username"]:
        return {"error": "not_logged_in"}
    data = await request.json()
    reviews = await load_reviews()
    # Remove existing review for this user/app
    reviews = [r for r in reviews if not (r["bundle_id"] == data["bundle_id"] and r["username"] == user["username"])]
    review = {
        "bundle_id": data["bundle_id"],
        "username": user["username"],
        "rating": data.get("rating", 0),
        "comment": data.get("comment", ""),
        "timestamp": int(time.time()),
        "reply": None,
        "reply_timestamp": None
    }
    reviews.append(review)
    await save_reviews(reviews)
    return {"ok": True}

@router.post("/api/reviews/reply")
async def api_reply_review(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["owner", "admin"]:
        return {"error": "forbidden"}
    data = await request.json()
    reviews = await load_reviews()
    found = False
    for r in reviews:
        if r["bundle_id"] == data["bundle_id"] and r["username"] == data["username"]:
            r["reply"] = data["reply"]
            r["reply_timestamp"] = int(time.time())
            found = True
            break
    if not found:
        return {"error": "notfound"}
    await save_reviews(reviews)
    # Log activity for admin reply
    activity = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "type": "reply_review",
        "bundle_id": data["bundle_id"],
        "review_user": data["username"],
        "reply": data["reply"],
        "admin": user["username"]
    }
    with open(os.path.join("logs", "activity.log"), "a") as f:
        f.write(json.dumps(activity) + "\n")
    return {"ok": True}
