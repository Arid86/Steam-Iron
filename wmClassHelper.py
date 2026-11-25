import logging
import os
import re
import subprocess

from configManager import ConfigManager

logger = logging.getLogger(__name__)

XDG_CACHE_HOME = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))

HOST_PROCESSES_PATH = "/proc"
FLATPAK_PROCESSES_PATH = os.path.join(XDG_CACHE_HOME, "steam-iron", "process_cache")

# configManager is used now and flatpak needs its own path.
#
# APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))
# IGNORED_PROCESSES_PATH = os.path.join(APPLICATION_PATH, "blacklists",
# "ignored_processes.json")

class WMClassHelper:
    def __init__(self):
        self.ConfigManager = ConfigManager()
        self.IGNORED_PROCESSES: list[str] = self.ConfigManager.get_full_ignored_processes()

# Old json load func - needs to be removed.
#
#     def _load_json(self) -> set[str]:
#         if not os.path.exists(IGNORED_PROCESSES_PATH):
#             logger.warning("ignored_processes.json not found. Proceeding with empty ignore #             list.")
#             return set()
#
#         try:
#             with open(IGNORED_PROCESSES_PATH, "r", encoding="utf-8") as file:
#                 data = json.load(file)
#                 if isinstance(data, list):
#                     return {str(item).lower() for item in data}
#         except (JSONDecodeError, OSError) as Error:
#             logger.warning("Failed to load ignored_processes.json: %s", Error)
#
#         return set()

    def get_processes(
        self,
        callback,
        steam_app_id: str | None,
        game_name: str | None,
    ) -> None:
        scanned_processes: list[dict[str,str]] = []

        PROCESSES_PATH = HOST_PROCESSES_PATH

        if os.path.exists("/.flatpak-info"):
            PROCESSES_PATH = FLATPAK_PROCESSES_PATH
            subprocess.run(
                [
                    "flatpak-spawn",
                    "--host",
                    "sh",
                    "-c",
                    (
                        f"rm -rf \"{FLATPAK_PROCESSES_PATH}\" && "
                        f"mkdir -p \"{FLATPAK_PROCESSES_PATH}\" && "
                        f"for p in /proc/[0-9]*; do "
                        f" [ -r \"$p/environ\" ] || continue; "
                        f" d=\"{FLATPAK_PROCESSES_PATH}/${{p#/proc/}}\"; "
                        f" mkdir -p \"$d\" && "
                        f" cp \"$p/comm\" \"$p/cmdline\" \"$p/environ\" \"$d/\" 2>/dev/null; "
                        f"done"
                    ),
                ],
                check=False,
            )

        if not os.path.exists(PROCESSES_PATH):
            callback([], "Unable to scan running processes.")
            return

        try:
            pids = [pid for pid in os.listdir(PROCESSES_PATH) if pid.isdigit()]
        except OSError as Error:
            logger.warning("Failed to list process pids: %s", Error)
            callback([], f"Failed to list process pids: {Error}")
            return

        for pid in pids:
            process_path = os.path.join(PROCESSES_PATH, pid)

            try:
                comm = ""
                comm_path = os.path.join(process_path, "comm")
                if os.path.exists(comm_path):
                    with open(comm_path, "r", encoding="utf-8", errors="ignore") as file:
                        comm = file.read().strip()

                cmdline = ""
                cmdline_args: list[str] = []
                cmdline_path = os.path.join(process_path, "cmdline")
                if os.path.exists(cmdline_path):
                    with open(cmdline_path, "rb") as file:
                        cmdline_raw = file.read()
                    cmdline_args = [
                        part.decode("utf-8", errors="ignore")
                        for part in cmdline_raw.split(b"\x00")
                        if part
                    ]
                    cmdline = " ".join(cmdline_args)

                environ = ""
                environ_args: list[str] = []
                environ_path = os.path.join(process_path, "environ")
                if os.path.exists(environ_path):
                    with open(environ_path, "rb") as file:
                        environ_raw = file.read()
                    environ_args = [
                        part.decode("utf-8", errors="ignore")
                        for part in environ_raw.split(b"\x00")
                        if part
                    ]
                    environ = " ".join(environ_args)

                appid = self._extract_appid(environ)
                wmclass = self._extract_wmclass(cmdline_args, environ_args, comm, appid)
                process_name = self._extract_process_name(cmdline_args)

                scanned_process = {
                    "pid": pid,
                    "title": process_name,
                    "comm": comm,
                    "cmdline": cmdline,
                    "environ": environ,
                    "wmclass": wmclass,
                    "steam_app_id": appid,
                }

                scanned_processes.append(scanned_process)

            except (OSError, PermissionError) as _Error:
                # logger.warning("Unable to parse process: %s", Error)
                continue

        filtered_processes = self._filter_processes(scanned_processes)
        deduplicated_processes = self._deduplicate_processes(
            key="title",
            filtered_processes=filtered_processes,
        )
        callback(deduplicated_processes, None)

    def _extract_appid(self, environ: str) -> str:
        match = re.search(r"(?:SteamAppId|SteamGameId|STEAM_COMPAT_APP_ID)=(\d+)", environ)
        if match:
            return match.group(1)

        return "N/A"

    def _extract_wmclass(self, cmdline_args: list[str], environ_args: list[str], comm: str = "", appid: str = "") -> str:
        is_wayland = "PROTON_ENABLE_WAYLAND=1" in environ_args
        is_valid_appid = appid not in ("", "0", "N/A")

        for arg in cmdline_args:
            if not arg or arg.startswith("-"):
                continue

            wmclass = self._normalize_path(arg)

            if wmclass.lower().endswith(".exe") and is_wayland and not self._proton_wayland_version(environ_args):
                return wmclass.lower()
            elif wmclass.lower().endswith(".exe") and is_valid_appid:
                return f"steam_app_{appid}"
            elif wmclass.lower().endswith(".exe"):
                return wmclass.lower()

            return wmclass

        return comm

    def _proton_wayland_version(self, environ_args: list[str]) -> bool:
        for entry in environ_args:
            if not entry.startswith("STEAM_COMPAT_TOOL_PATHS="):
                continue

            proton_directory = entry.split("=", 1)[1].split(":", 1)[0]

            for path in (
                "files/lib/wine/x86_64-unix/winewayland.so",
                "files/lib64/wine/x86_64-unix/winewayland.so",
                "files/lib/wine/x86_64-unix/winewayland.drv.so",
                "files/lib64/wine/x86_64-unix/winewayland.drv.so",
            ):
                so_path = os.path.join(proton_directory, path)
                if os.path.exists(so_path):
                    with open(so_path, "rb") as file:
                        return b"steam_app_" in file.read()

        return False

    def _extract_process_name(self, cmdline_args: list[str], comm: str = "") -> str:
        for arg in cmdline_args:
            if not arg or arg.startswith("-"):
                continue

            process_name = self._normalize_path(arg)
            if not process_name:
                continue

            clean_name = re.sub(
                r"\.(exe|x86_64|x86|sh|bin|elf)$", "", process_name, flags=re.IGNORECASE
            )

            return clean_name

        return comm

    def _normalize_path(self, arg_path: str) -> str:
        normalized_path = arg_path.replace("\\", "/")
        return os.path.basename(normalized_path)

    def _filter_processes(
        self,
        scanned_processes: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        filtered_processes = []
        for process in scanned_processes:
            if process["steam_app_id"] != "N/A" and process["title"] not in self.IGNORED_PROCESSES:
                filtered_processes.append(process)

        return filtered_processes

    def _deduplicate_processes(
        self,
        key: str,
        filtered_processes: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        duplicate: set[str] = set()
        unique_processes: list[dict[str, str]] = []

        for process in filtered_processes:
            process_key = process.get(key)

            if not process_key:
                continue

            if process_key not in duplicate:
                duplicate.add(process_key)
                unique_processes.append(process)

        return unique_processes
