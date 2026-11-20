import json
import logging
import os

import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

SERVICE_NAME = "steam-iron"
KEY_NAME = "steamgriddb_api_key"

APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))

XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
USER_CONFIG_PATH = os.path.join(XDG_CONFIG_HOME, "steam-iron")

os.makedirs(USER_CONFIG_PATH, exist_ok=True)
CONFIG_PATH = os.path.join(USER_CONFIG_PATH, "config.json")

DEFAULT_IGNORED_SHORTCUTS_PATH = os.path.join(
    APPLICATION_PATH,
    "blacklists",
    "ignored_shortcuts.json"
)
DEFAULT_IGNORED_PROCESSES_PATH = os.path.join(
    APPLICATION_PATH,
    "blacklists",
    "ignored_processes.json"
)
USER_IGNORED_SHORTCUTS_PATH = os.path.join(
    USER_CONFIG_PATH,
    "user",
    "user_ignored_shortcuts.json"
)
USER_IGNORED_PROCESSES_PATH = os.path.join(
    USER_CONFIG_PATH,
    "user",
    "user_ignored_processes.json"
)

class ConfigManager:
    def __init__(self):
        pass

    def get_api_key(self) -> str:
        env_key = os.environ.get("STEAMGRIDDB_API_KEY")
        if env_key:
            return env_key.strip();

        try:
            secret = keyring.get_password(SERVICE_NAME, KEY_NAME)
            return secret if secret is not None else ""
        except KeyringError as Error:
            logger.warning("Failed to retrieve API Key from keyring: %s", Error)
            return ""

    def set_api_key(self, api_key: str) -> bool:
        key = api_key.strip()

        try:
            if not key:
                try:
                    keyring.delete_password(SERVICE_NAME, KEY_NAME)
                except KeyringError as Error:
                    logger.warning("Failed to delete API Key from keyring: %s", Error)
                return True

            keyring.set_password(SERVICE_NAME, KEY_NAME, key)
            return True
        except KeyringError as Error:
            logger.error("Failed to save API Key to keyring: %s", Error)
            return False

# Old api_key saving, using keyring now.
#
#     def get_api_key(self) -> str:
#         if os.path.exists(CONFIG_PATH):
#             try:
#                 with open(CONFIG_PATH, "r", encoding="utf-8") as file:
#                     return json.load(file).get("api_key", "")
#             except (json.JSONDecodeError, OSError) as Error:
#                 logger.warning("Failed to load config.json: %s", Error)
#
#         return ""
#
#     def set_api_key(self, api_key: str) -> None:
#         data = {"api_key": api_key.strip()}
#
#         try:
#             os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
#
#             with open(CONFIG_PATH, "w", encoding="utf-8") as file:
#                 json.dump(data, file, indent=2)
#         except OSError as Error:
#             logger.error("Failed to save config.json: %s", Error)

    def _load_list(self, path: str) -> list[str]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    if isinstance(data, list):
                        return [str(item).strip() for item in data if item]
            except (json.JSONDecodeError, OSError) as Error:
                logger.warning("Failed to load %s: %s", path, Error)

        return []

    def _save_list(self, path: str, items: list[str]) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, "w", encoding="utf-8") as file:
                json.dump(sorted(set(items)), file, indent=2)
        except OSError as Error:
            logger.error("Failed to save %s: %s", path, Error)

    def get_default_ignored_shortcuts(self) -> list[str]:
        return self._load_list(DEFAULT_IGNORED_SHORTCUTS_PATH)

    def get_user_ignored_shortcuts(self) -> list[str]:
        return self._load_list(USER_IGNORED_SHORTCUTS_PATH)

    def get_full_ignored_shortcuts(self) -> list[str]:
        defaults = self.get_default_ignored_shortcuts()
        user_list = self.get_user_ignored_shortcuts()

        full_ignored_shortcuts_normalized = set()
        for item in defaults + user_list:
            item = item.strip()
            if not item:
                continue
            if not item.lower().endswith(".desktop"):
                item = f"{item}.desktop"
            full_ignored_shortcuts_normalized.add(item)

        return sorted(full_ignored_shortcuts_normalized)

    def add_user_ignored_shortcut(self, item: str) -> bool:
        item = item.strip()
        defaults = self.get_default_ignored_shortcuts()
        user_list = self.get_user_ignored_shortcuts()

        if item in defaults or item in user_list:
            return False

        user_list.append(item)
        self._save_list(USER_IGNORED_SHORTCUTS_PATH, user_list)

        return True

    def remove_user_ignored_shortcut(self, item: str) -> bool:
        user_list = self.get_user_ignored_shortcuts()
        if item in user_list:
            user_list.remove(item)
            self._save_list(USER_IGNORED_SHORTCUTS_PATH, user_list)
            return True

        return False

    def get_default_ignored_processes(self) -> list[str]:
        return self._load_list(DEFAULT_IGNORED_PROCESSES_PATH)

    def get_user_ignored_processes(self) -> list[str]:
        return self._load_list(USER_IGNORED_PROCESSES_PATH)

    def get_full_ignored_processes(self) -> list[str]:
        defaults = self.get_default_ignored_processes()
        user_list = self.get_user_ignored_processes()
        return list(set(defaults + user_list))

    def add_user_ignored_process(self, item: str) -> bool:
        item = item.strip().lower()
        defaults = self.get_default_ignored_processes()
        user_list = self.get_user_ignored_processes()

        if item in defaults or item in user_list:
            return False

        user_list.append(item)
        self._save_list(USER_IGNORED_PROCESSES_PATH, user_list)

        return True

    def remove_user_ignored_process(self, item: str) -> bool:
        user_list = self.get_user_ignored_processes()
        if item in user_list:
            user_list.remove(item)
            self._save_list(USER_IGNORED_PROCESSES_PATH, user_list)
            return True

        return False
