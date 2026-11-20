# gridDBHelper.py
# pyright: reportAttributeAccessIssue=false
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from gi.repository import Gio, GLib

from configManager import ConfigManager

logger = logging.getLogger(__name__)

# Old development directories, moved everything to XDG user directories.
#
# APPLICATION_DIR = os.path.dirname(os.path.abspath(__file__))
# ICON_CACHE_DIR = os.path.join(APPLICATION_DIR, "griddb_cache", "icons")
# JSON_CACHE_DIR = os.path.join(APPLICATION_DIR, "griddb_cache", "json")
# ICONS_DIR = os.path.join(APPLICATION_DIR, "icons")

XDG_CACHE_HOME = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))

CACHE_BASE_PATH = os.path.join(XDG_CACHE_HOME, "steam-iron", "griddb_cache")
ICON_CACHE_DIR = os.path.join(CACHE_BASE_PATH, "icons")
JSON_CACHE_DIR = os.path.join(CACHE_BASE_PATH, "json")

ICONS_DIR = os.path.join(XDG_CONFIG_HOME, "steam-iron", "icons")

for directory in [ICON_CACHE_DIR, JSON_CACHE_DIR, ICONS_DIR]:
    gio_dir = Gio.File.new_for_path(directory)
    if not gio_dir.query_exists():
        gio_dir.make_directory_with_parents(None)

BASE_URL = "https://www.steamgriddb.com/api/v2"
CACHE_TTL_DAYS = 7
CACHE_TTL_SECONDS = int(timedelta(days=CACHE_TTL_DAYS).total_seconds())

class SteamGridDBHelper:
    def __init__(self, api_key: str | None = None):
        # Used for testing
        # DEFAULT_KEY = ""

        self.ConfigManager = ConfigManager()
        self.api_key = api_key or self.ConfigManager.get_api_key()

    def _get_headers(self) -> dict[str,str]:
        print(f"[DEBUG] Using API Key: '{self.api_key}'")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Steam-Iron/0.4"
        }

    def _read_json_cache(self, cache_filename: str, max_age_seconds: int = CACHE_TTL_SECONDS) -> dict[str, object] | list[dict[str, object]] | None:
        cache_path = os.path.join(JSON_CACHE_DIR, cache_filename)

        if os.path.exists(cache_path):
            cache_age = time.time() - os.path.getmtime(cache_path)

            if cache_age > max_age_seconds:
                logger.info("Cache expired for %s (Age: %.1f hours)", cache_filename, cache_age / 3600)
                return None

            try:
                with open(cache_path, "r", encoding="utf-8") as file:
                    return json.load(file)
            except (json.JSONDecodeError, OSError) as Error:
                logger.warning("Failed reading cached JSON %s: %s", cache_filename, Error)

        return None

    def _write_json_cache(self, cache_filename: str, data: dict[str, object] | list[dict[str, object]]) -> None:
        cache_path = os.path.join(JSON_CACHE_DIR, cache_filename)

        try:
            with open(cache_path, "w", encoding="utf-8") as file:
                json.dump(data, file)
        except OSError as Error:
            logger.warning("Failed writing cached JSON %s: %s", cache_filename, Error)

    def search_id(self, steam_app_id: str) -> int | None:
        cache_key = f"game_{steam_app_id}.json"
        cache_data = self._read_json_cache(cache_key)

        if isinstance(cache_data, dict) and "id" in cache_data:
            game_id = cache_data["id"]
            if isinstance(game_id, int):
                return game_id

        if not self.api_key:
            logger.warning("Missing SteamGridDB API key.")
            return None

        url = f"{BASE_URL}/games/steam/{steam_app_id}"
        request = urllib.request.Request(url, headers=self._get_headers())

        try:
            with urllib.request.urlopen(request) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("success") and data.get("data"):
                    game_data = data["data"]
                    self._write_json_cache(cache_key, game_data)
                    return game_data.get("id")
        except urllib.error.URLError as Error:
            logger.error("Error querying SteamGridDB API: %s", Error)

        return None

    def fetch_icons(self, sgdb_game_id: int) -> list[dict[str, object]]:
        cache_key = f"icons_{sgdb_game_id}.json"
        cache_icons = self._read_json_cache(cache_key)

        if isinstance(cache_icons, list):
            return cache_icons

        if not self.api_key:
            return []

        url = f"{BASE_URL}/icons/game/{sgdb_game_id}"
        request = urllib.request.Request(url, headers=self._get_headers())

        try:
            with urllib.request.urlopen(request) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("success"):
                    icons_list = data.get("data", [])
                    self._write_json_cache(cache_key, icons_list)
                    return icons_list
        except urllib.error.URLError as Error:
            logger.error("Error fetching icons for: %s Error: %s", sgdb_game_id, Error)
        return []

    def download_icons(self, icon_id: int, icon_url: str) -> str | None:
        ext = os.path.splitext(icon_url)[-1] or ".png"
        target_path = os.path.join(ICON_CACHE_DIR, f"{icon_id}{ext}")
        target_file = Gio.File.new_for_path(target_path)

        if target_file.query_exists():
            return target_path

        try:
            cdn_headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            request = urllib.request.Request(icon_url, headers=cdn_headers)
            with urllib.request.urlopen(request) as response:
                data = response.read()

            out_stream = target_file.replace(None, False, Gio.FileCreateFlags.NONE, None)
            out_stream.write_all(data, None)
            out_stream.close(None)

            return target_path
        except (urllib.error.URLError, GLib.Error) as Error:
            logger.error("Error downloading icon %s: %s", icon_id, Error)
            return None

    def copy_icon(self, source_path: str, steam_app_id: str) -> str:
        ext = os.path.splitext(source_path)[-1] or ".png"
        game_id = "".join(c for c in steam_app_id if c.isalnum() or c in ("-", "_")).strip()
        filename = f"game_{game_id}{ext}"

        target_path = os.path.join(ICONS_DIR, filename)

        source_file = Gio.File.new_for_path(source_path)
        target_file = Gio.File.new_for_path(target_path)

        source_file.copy(target_file, Gio.FileCopyFlags.OVERWRITE, None, None)
        return target_path

    def cached_icon(self, icon_id: int, image_url: str) -> bool:
        ext = os.path.splitext(image_url)[-1] or ".png"
        target_path = os.path.join(ICON_CACHE_DIR, f"{icon_id}{ext}")
        return Gio.File.new_for_path(target_path).query_exists()
