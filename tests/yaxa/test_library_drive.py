"""Walking the shared Drive library with a fake Drive service."""

from __future__ import annotations

import re

from deeptutor.yaxa.library.drive import FOLDER, walk

PDF = "application/pdf"
SHORTCUT = "application/vnd.google-apps.shortcut"


class _Req:
    def __init__(self, result):
        self._result = result

    def execute(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeFiles:
    """files() of a Drive v3 client over {folder_id: [file dicts]} with 2-item pages."""

    def __init__(self, tree, others):
        self.tree, self.others = tree, others

    def list(self, q, pageToken=None, **_):
        parent = re.match(r"'([^']+)' in parents", q).group(1)
        assert "trashed=false" in q
        items = self.tree.get(parent, [])
        start = int(pageToken or 0)
        page = {"files": items[start : start + 2]}
        if start + 2 < len(items):
            page["nextPageToken"] = str(start + 2)
        return _Req(page)

    def get(self, fileId, **_):
        found = self.others.get(fileId)
        return _Req(found if found else PermissionError("404 File not found"))


class FakeService:
    def __init__(self, tree, others):
        self._files = FakeFiles(tree, others)

    def files(self):
        return self._files


def _f(id_, name, mime=PDF, **extra):
    return {"id": id_, "name": name, "mimeType": mime, "md5Checksum": f"md5-{id_}",
            "modifiedTime": "2026-10-22T00:00:00Z", "size": "10"} | extra


def test_walk_builds_paths_follows_pages_and_shortcuts() -> None:
    tree = {
        "root": [_f("g", "GCPP", FOLDER)],
        "g": [_f("d", "DFA Defence and Foreign Affairs", FOLDER)],
        "d": [_f("m", "DFA-AS Introduction to Arthashastra", FOLDER)],
        "m": [_f("r", "Readings", FOLDER)],
        "r": [_f("a", "CS22 - A.pdf"), _f("b", "CS23 - B.pdf"), _f("c", "CS24 - C.pdf"),
              _f("s", "linked.pdf", SHORTCUT, shortcutDetails={"targetId": "t"}),
              _f("u", "gone.pdf", SHORTCUT, shortcutDetails={"targetId": "missing"})],
    }
    others = {"t": _f("t", "Original name.pdf")}
    files = {f.name: f for f in walk(FakeService(tree, others), "root")}
    assert set(files) == {"CS22 - A.pdf", "CS23 - B.pdf", "CS24 - C.pdf", "linked.pdf", "gone.pdf"}
    assert files["CS24 - C.pdf"].path == ("GCPP", "DFA Defence and Foreign Affairs",
                                          "DFA-AS Introduction to Arthashastra", "Readings")
    assert (files["linked.pdf"].id, files["linked.pdf"].md5) == ("t", "md5-t")  # [RF2] target, shortcut's own name
    assert files["gone.pdf"].mime == "shortcut/unreadable"
    assert files["CS22 - A.pdf"].size == 10
