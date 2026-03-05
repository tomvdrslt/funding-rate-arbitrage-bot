import io
import logging
import os
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError

from auth import get_credentials
from config import DRIVE_FOLDER_NAME

logger = logging.getLogger(__name__)


class DriveClient:
    def __init__(self):
        creds = get_credentials()
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._root_folder_id: Optional[str] = None
        # Cache: relative_path -> file_id
        self._file_id_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Folder helpers
    # ------------------------------------------------------------------

    def _get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = (
            self._service.files()
            .list(q=query, fields="files(id)", spaces="drive")
            .execute()
        )
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = self._service.files().create(body=metadata, fields="id").execute()
        logger.debug("Created Drive folder '%s' id=%s", name, folder["id"])
        return folder["id"]

    def get_root_folder_id(self) -> str:
        if self._root_folder_id is None:
            self._root_folder_id = self._get_or_create_folder(DRIVE_FOLDER_NAME)
        return self._root_folder_id

    def _ensure_folder_path(self, rel_dir: str) -> str:
        """Ensure all folders in a relative path exist, return leaf folder id."""
        parts = rel_dir.replace("\\", "/").strip("/").split("/")
        parent_id = self.get_root_folder_id()
        for part in parts:
            if part:
                parent_id = self._get_or_create_folder(part, parent_id)
        return parent_id

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _get_file_id(self, rel_path: str) -> Optional[str]:
        if rel_path in self._file_id_cache:
            return self._file_id_cache[rel_path]

        rel_dir = os.path.dirname(rel_path)
        filename = os.path.basename(rel_path)
        parent_id = self._ensure_folder_path(rel_dir) if rel_dir else self.get_root_folder_id()

        query = f"name='{filename}' and '{parent_id}' in parents and trashed=false"
        results = (
            self._service.files()
            .list(q=query, fields="files(id)", spaces="drive")
            .execute()
        )
        files = results.get("files", [])
        if files:
            file_id = files[0]["id"]
            self._file_id_cache[rel_path] = file_id
            return file_id
        return None

    def upload(self, local_path: str, rel_path: str) -> None:
        """Upload local_path to Drive at rel_path (relative to OrcaSlicerSync root)."""
        rel_dir = os.path.dirname(rel_path)
        filename = os.path.basename(rel_path)
        parent_id = self._ensure_folder_path(rel_dir) if rel_dir else self.get_root_folder_id()

        with open(local_path, "rb") as f:
            content = f.read()

        media = MediaIoBaseUpload(
            io.BytesIO(content), mimetype="application/octet-stream", resumable=False
        )

        existing_id = self._get_file_id(rel_path)
        try:
            if existing_id:
                self._service.files().update(
                    fileId=existing_id,
                    media_body=media,
                    fields="id,modifiedTime",
                ).execute()
                logger.info("Updated Drive file: %s", rel_path)
            else:
                metadata = {"name": filename, "parents": [parent_id]}
                result = (
                    self._service.files()
                    .create(body=metadata, media_body=media, fields="id,modifiedTime")
                    .execute()
                )
                self._file_id_cache[rel_path] = result["id"]
                logger.info("Uploaded new Drive file: %s", rel_path)
        except HttpError as e:
            logger.error("Upload failed for %s: %s", rel_path, e)
            raise

    def download(self, file_id: str, local_path: str) -> None:
        """Download a Drive file by id to local_path."""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        request = self._service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        with open(local_path, "wb") as f:
            f.write(buf.getvalue())
        logger.info("Downloaded Drive file to: %s", local_path)

    # ------------------------------------------------------------------
    # Changes API
    # ------------------------------------------------------------------

    def get_start_page_token(self) -> str:
        response = self._service.changes().getStartPageToken().execute()
        return response["startPageToken"]

    def poll_changes(self, page_token: str) -> tuple[list[dict], str]:
        """
        Returns (list_of_changed_files, new_page_token).
        Each item: {"id": str, "name": str, "modifiedTime": str, "parents": [...], "trashed": bool}
        """
        changed = []
        new_token = page_token

        while True:
            response = (
                self._service.changes()
                .list(
                    pageToken=new_token,
                    spaces="drive",
                    fields="nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,parents,modifiedTime,trashed,mimeType))",
                    includeRemoved=False,
                )
                .execute()
            )

            for change in response.get("changes", []):
                if change.get("removed"):
                    continue
                f = change.get("file")
                if f and not f.get("trashed") and f.get("mimeType") != "application/vnd.google-apps.folder":
                    changed.append(f)

            if "nextPageToken" in response:
                new_token = response["nextPageToken"]
            else:
                new_token = response.get("newStartPageToken", new_token)
                break

        return changed, new_token

    def list_all_files(self) -> list[tuple[str, str, str]]:
        """Return [(file_id, rel_path, modifiedTime)] for all files under OrcaSlicerSync."""
        results: list[tuple[str, str, str]] = []
        self._walk_folder(self.get_root_folder_id(), "", results)
        return results

    def _walk_folder(self, folder_id: str, rel_prefix: str, results: list) -> None:
        page_token = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="nextPageToken,files(id,name,mimeType,modifiedTime)",
                    pageToken=page_token,
                    spaces="drive",
                )
                .execute()
            )
            for f in resp.get("files", []):
                rel_path = f["name"] if not rel_prefix else f"{rel_prefix}/{f['name']}"
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    self._walk_folder(f["id"], rel_path, results)
                else:
                    results.append((f["id"], rel_path, f.get("modifiedTime", "")))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def get_file_metadata(self, file_id: str) -> dict:
        return (
            self._service.files()
            .get(fileId=file_id, fields="id,name,parents,modifiedTime")
            .execute()
        )

    def resolve_path(self, file_id: str) -> Optional[str]:
        """
        Walk parent chain to build a path relative to OrcaSlicerSync root.
        Returns None if the file is not under OrcaSlicerSync.
        """
        root_id = self.get_root_folder_id()

        def _get_name_and_parents(fid: str) -> tuple[str, list[str]]:
            meta = (
                self._service.files()
                .get(fileId=fid, fields="name,parents")
                .execute()
            )
            return meta.get("name", ""), meta.get("parents", [])

        parts = []
        current_id = file_id
        for _ in range(10):  # max depth guard
            name, parents = _get_name_and_parents(current_id)
            if current_id == root_id:
                break
            parts.append(name)
            if not parents:
                return None  # not under our root
            current_id = parents[0]
            if current_id == root_id:
                break
        else:
            return None

        if current_id != root_id:
            return None

        return os.path.join(*reversed(parts)) if parts else None
