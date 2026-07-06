from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import frappe


APP_ROOT = Path(__file__).resolve().parents[2]
TRAINING_DOCS_ROOT = APP_ROOT / "docs" / "training" / "veterinary_doctor_operations"
TRAINING_MODULES_PATH = TRAINING_DOCS_ROOT / "training_modules.json"

ADMIN_TRAINING_ROLES = {"System Manager", "VetEdge Administrator", "Branch Manager", "VetEdge Branch Manager"}
DOCTOR_TRAINING_ROLES = {"VetEdge Doctor", "Veterinary Doctor"}
ALLOWED_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"}
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")
VIDEO_STATUSES = {"Not Recorded", "Recorded", "Published", "Needs Review"}


def _training_error(message: str, exc=frappe.ValidationError):
	frappe.throw(message, exc)


def get_user_training_roles(user: str | None = None) -> set[str]:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return set()
	return set(get_roles(user))


def load_training_manifest() -> list[dict]:
	if not TRAINING_MODULES_PATH.exists():
		_training_error("Training module setup was not found.")

	try:
		raw_modules = json.loads(TRAINING_MODULES_PATH.read_text(encoding="utf-8"))
	except json.JSONDecodeError:
		_training_error("Training module setup is not valid JSON.")

	if not isinstance(raw_modules, list):
		_training_error("Training module setup must contain a list of modules.")

	modules = [normalize_manifest_row(row) for row in raw_modules]
	return sorted(modules, key=lambda row: (int(row.get("order") or 0), row.get("title") or ""))


def normalize_manifest_row(row: dict) -> dict:
	if not isinstance(row, dict):
		_training_error("Training module setup contains an invalid row.")

	required = ("module_id", "title", "role_group", "markdown_path", "short_description", "youtube_url", "video_title", "video_status", "status", "order")
	for fieldname in required:
		if row.get(fieldname) is None:
			_training_error(f"Training module setup row is missing {fieldname}.")

	video_status = str(row.get("video_status") or "").strip()
	if video_status not in VIDEO_STATUSES:
		_training_error("Training video status needs review.")

	module = {
		"module_id": str(row["module_id"]).strip(),
		"title": str(row["title"]).strip(),
		"role_group": str(row["role_group"]).strip(),
		"short_description": str(row.get("short_description") or row.get("description") or "").strip(),
		"markdown_path": str(row["markdown_path"]).strip(),
		"youtube_url": str(row.get("youtube_url") or "").strip(),
		"video_title": str(row.get("video_title") or "").strip(),
		"video_status": video_status,
		"status": str(row["status"]).strip(),
		"order": int(row.get("order") or 0),
	}
	module["has_video"] = bool(get_safe_youtube_embed_url(module["youtube_url"]))
	module["video_embed_url"] = get_safe_youtube_embed_url(module["youtube_url"])
	module["video_display_status"] = get_video_display_status(module["youtube_url"], module["video_status"])
	return module


def can_view_training_module(module: dict, user: str | None = None) -> bool:
	roles = get_user_training_roles(user)
	if roles & ADMIN_TRAINING_ROLES:
		return True
	if module.get("role_group") == "Doctor Operations" and roles & DOCTOR_TRAINING_ROLES:
		return True
	return False


def get_visible_training_modules(user: str | None = None) -> list[dict]:
	return [
		public_module_payload(module)
		for module in load_training_manifest()
		if module.get("status") == "Published" and can_view_training_module(module, user=user)
	]


def public_module_payload(module: dict) -> dict:
	return {
		"module_id": module["module_id"],
		"title": module["title"],
		"role_group": module["role_group"],
		"short_description": module.get("short_description") or "",
		"status": module["status"],
		"order": module["order"],
		"has_video": module.get("has_video", False),
		"video_title": module.get("video_title") or "",
		"video_status": module.get("video_status") or "Not Recorded",
		"video_display_status": module.get("video_display_status") or "Video coming soon",
		"video_embed_url": module.get("video_embed_url") or "",
	}


def get_module_by_id(module_id: str) -> dict:
	module_id = str(module_id or "").strip()
	if not module_id:
		_training_error("Training module is required.")

	for module in load_training_manifest():
		if module["module_id"] == module_id:
			return module

	_training_error("Training module was not found.", frappe.DoesNotExistError)


def resolve_markdown_path(module: dict) -> Path:
	markdown_path = Path(module.get("markdown_path") or "")
	if markdown_path.is_absolute():
		_training_error("Training module path must be relative.")
	if ".." in markdown_path.parts:
		_training_error("Training module path is not allowed.")
	if markdown_path.suffix.lower() != ".md":
		_training_error("Training module must point to a Markdown file.")

	resolved = (APP_ROOT / markdown_path).resolve()
	training_root = TRAINING_DOCS_ROOT.resolve()
	if not resolved.is_relative_to(training_root):
		_training_error("Training module path is outside the approved training folder.")
	return resolved


def read_training_markdown(module: dict) -> str:
	path = resolve_markdown_path(module)
	if not path.exists():
		_training_error(f"Training guide file was not found: {path.name}", frappe.DoesNotExistError)
	return path.read_text(encoding="utf-8")


def get_video_display_status(url: str | None, video_status: str | None = None) -> str:
	if not url:
		return "Video coming soon"
	if get_safe_youtube_embed_url(url):
		return "Video available" if video_status != "Needs Review" else "Video link needs review"
	return "Video link needs review"


def get_safe_youtube_embed_url(url: str | None) -> str:
	url = (url or "").strip()
	if not url:
		return ""

	parsed = urlparse(url)
	if parsed.scheme not in {"https", "http"}:
		return ""

	host = (parsed.netloc or "").lower()
	if host not in ALLOWED_YOUTUBE_HOSTS:
		return ""

	video_id = ""
	if host in {"youtu.be", "www.youtu.be"}:
		video_id = parsed.path.strip("/").split("/")[0]
	elif parsed.path.startswith("/watch"):
		video_id = parse_qs(parsed.query).get("v", [""])[0]
	elif parsed.path.startswith("/embed/"):
		video_id = parsed.path.split("/embed/", 1)[1].split("/")[0]

	if not video_id or not YOUTUBE_ID_RE.match(video_id):
		return ""

	return f"https://www.youtube-nocookie.com/embed/{video_id}"


def extract_practice_exercise(markdown: str) -> str:
	return extract_first_heading_section(markdown, {"practice exercise", "practical exercise"})


def extract_screenshot_references(markdown: str) -> list[dict]:
	refs = []
	for alt, path in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", markdown or ""):
		refs.append({"alt": alt.strip(), "path": path.strip()})
	return refs


def extract_first_heading_section(markdown: str, headings: set[str]) -> str:
	lines = (markdown or "").splitlines()
	start = None
	start_level = 0
	for idx, line in enumerate(lines):
		match = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
		if match and match.group(2).strip().lower() in headings:
			start = idx
			start_level = len(match.group(1))
			break
	if start is None:
		return ""

	end = len(lines)
	for idx in range(start + 1, len(lines)):
		match = re.match(r"^(#{2,6})\s+", lines[idx])
		if match and len(match.group(1)) <= start_level:
			end = idx
			break
	return "\n".join(lines[start:end]).strip()


@frappe.whitelist()
def get_training_modules() -> list[dict]:
	return get_visible_training_modules()


@frappe.whitelist()
def get_training_module_content(module_id: str) -> dict:
	module = get_module_by_id(module_id)
	if module.get("status") != "Published" or not can_view_training_module(module):
		_training_error("You are not permitted to view this training module.", frappe.PermissionError)

	markdown = read_training_markdown(module)
	return {
		"module": public_module_payload(module),
		"markdown": markdown,
		"practice_exercise": extract_practice_exercise(markdown),
		"screenshots": extract_screenshot_references(markdown),
	}
