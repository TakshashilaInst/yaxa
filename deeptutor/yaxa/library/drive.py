"""Read-only access to the shared Drive library through a Google service account.

The service account is a Viewer on the library folder only, so it can't see
the rest of the shared drive. ``walk`` lists every file under the library
with its folder path; ``download`` streams one file to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
_FIELDS = "id,name,mimeType,md5Checksum,modifiedTime,size,shortcutDetails"


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    path: tuple[str, ...]  # folder names from the library root down, e.g. ("GCPP", "Core", ...)
    mime: str
    md5: str = ""
    modified: str = ""
    size: int = 0


def service(key_file: Path) -> Any:
    """A Drive v3 client signed in as the library service account (read-only)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        str(key_file), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _children(svc: Any, folder_id: str) -> list[dict]:
    out, token = [], None
    while True:
        page = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields=f"nextPageToken, files({_FIELDS})",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
            pageToken=token,
        ).execute()
        out.extend(page.get("files", []))
        token = page.get("nextPageToken")
        if not token:
            return out


def _file(item: dict, path: tuple[str, ...], name: str | None = None) -> DriveFile:
    return DriveFile(
        id=item["id"],
        name=name or item["name"],
        path=path,
        mime=item.get("mimeType", ""),
        md5=item.get("md5Checksum", ""),
        modified=item.get("modifiedTime", ""),
        size=int(item.get("size") or 0),
    )


def walk(svc: Any, root_id: str) -> list[DriveFile]:
    """Every file under the library root, depth first. Shortcuts resolve to their target."""
    files: list[DriveFile] = []
    stack: list[tuple[str, tuple[str, ...]]] = [(root_id, ())]
    while stack:
        folder_id, path = stack.pop()
        for item in _children(svc, folder_id):
            mime = item.get("mimeType", "")
            if mime == FOLDER:
                stack.append((item["id"], path + (item["name"],)))
            elif mime == SHORTCUT:
                target = (item.get("shortcutDetails") or {}).get("targetId", "")
                try:
                    real = svc.files().get(fileId=target, fields=_FIELDS, supportsAllDrives=True).execute()
                except Exception:  # target not shared with the service account, or deleted
                    files.append(DriveFile(id=item["id"], name=item["name"], path=path, mime="shortcut/unreadable"))
                    continue
                # keep the shortcut's own name: that's what staff typed in the library
                files.append(_file(real, path, name=item["name"]))
            else:
                files.append(_file(item, path))
    return files


def download(svc: Any, file_id: str, dest: Path) -> Path:
    """Stream a Drive file to `dest` (written to a .part file, then renamed)."""
    from googleapiclient.http import MediaIoBaseDownload

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    with part.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=32 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    part.replace(dest)
    return dest
