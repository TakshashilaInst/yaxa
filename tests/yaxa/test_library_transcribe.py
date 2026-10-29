"""Transcription for the library: Sarvam for the words, Zoom for who spoke."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.yaxa.library import transcribe as tr

VTT = """WEBVTT

1
00:00:01.000 --> 00:00:04.500
Kajari Kamal: Good evening, everyone.

2
00:00:05.000 --> 00:00:07.000
ravi.k: Ma'am, is saptanga still relevant?

3
00:01:02.250 --> 00:01:03.000
no speaker label here
"""


def test_parse_vtt() -> None:
    s = tr.parse_vtt(VTT)
    assert s[0] == {"start": 1.0, "end": 4.5, "text": "Good evening, everyone.", "speaker": "Kajari Kamal"}
    assert (s[1]["speaker"], s[1]["text"]) == ("ravi.k", "Ma'am, is saptanga still relevant?")
    assert (s[2]["start"], s[2]["speaker"], s[2]["text"]) == (62.25, "", "no speaker label here")


def test_chunks_for_long_recording() -> None:  # [RF3]
    assert tr.chunks_for(3 * 3600) == [(0.0, 6900.0), (6900.0, 10800.0)]
    assert tr.chunks_for(600) == [(0.0, 600.0)]


class FakeJob:
    def __init__(self, outputs: dict[str, dict]) -> None:
        self.outputs, self.uploaded = outputs, []

    state = "Completed"

    def upload_files(self, file_paths, timeout=60.0):
        self.uploaded = list(file_paths)

    def start(self):
        pass

    def wait_until_complete(self, **_):
        return type("Status", (), {"job_state": self.state})()

    def download_outputs(self, output_dir):  # like sarvamai 0.1.40: "<input file name>.json"
        for path in self.uploaded:
            if Path(path).name in self.outputs:
                Path(output_dir, Path(path).name + ".json").write_text(json.dumps(self.outputs[Path(path).name]))


class FakeClient:
    def __init__(self, outputs):
        self.job = FakeJob(outputs)
        self.kwargs = {}
        outer = self

        class STT:
            def create_job(self, **kwargs):
                outer.kwargs = kwargs
                return outer.job

        self.speech_to_text_job = STT()


def _entry(text, start, end, spk="0"):
    return {"transcript": text, "start_time_seconds": start, "end_time_seconds": end, "speaker_id": spk}


def test_sarvam_offsets_each_chunk(tmp_path: Path) -> None:  # [RF3]
    a, b = tmp_path / "chunk_000.mp3", tmp_path / "chunk_001.mp3"
    client = FakeClient({
        "chunk_000.mp3": {"diarized_transcript": {"entries": [_entry("first part", 1, 2)]}},
        "chunk_001.mp3": {"diarized_transcript": {"entries": [_entry("second part", 1, 2, "1")]}},
    })
    segs = tr.sarvam_transcribe([(a, 0.0), (b, 6900.0)], [f"term {i}" for i in range(80)] + ["term 1"], "key", client=client, work=tmp_path)
    assert [(s["start"], s["text"], s["speaker"]) for s in segs] == [(1.0, "first part", "S0"), (6901.0, "second part", "S1")]
    assert client.kwargs["model"] == "saaras:v4" and client.kwargs["with_diarization"] is True
    assert len(client.kwargs["keyterms"]) == 50


def test_sarvam_without_diarisation_uses_timestamps(tmp_path: Path) -> None:
    client = FakeClient({"chunk_000.mp3": {"transcript": "a b", "timestamps": {
        "chunks": ["a", "b"], "start_time_seconds": [0, 2], "end_time_seconds": [1, 3]}}})
    segs = tr.sarvam_transcribe([(tmp_path / "chunk_000.mp3", 0.0)], [], "key", client=client, work=tmp_path)
    assert [(s["start"], s["text"]) for s in segs] == [(0.0, "a"), (2.0, "b")]


def test_merge_speakers_by_overlap() -> None:
    sarvam = [{"start": 1, "end": 4, "text": "Good evening everyone", "speaker": "S0"},
              {"start": 5, "end": 7, "text": "is saptanga still relevant", "speaker": "S1"},
              {"start": 300, "end": 301, "text": "silence in zoom", "speaker": "S0"}]
    out = tr.merge_speakers(sarvam, tr.parse_vtt(VTT))
    assert [s["speaker"] for s in out] == ["Kajari Kamal", "ravi.k", ""]
    assert out[0]["text"] == "Good evening everyone"  # Sarvam's words are kept


def _stub_media(monkeypatch, tmp_path):
    monkeypatch.setattr(tr, "extract_audio", lambda media, out: ([(tmp_path / "chunk_000.mp3", 0.0)], 10.0))


def test_transcribe_prefers_sarvam_with_zoom_speakers(monkeypatch, tmp_path: Path) -> None:
    _stub_media(monkeypatch, tmp_path)
    monkeypatch.setattr(tr, "sarvam_transcribe", lambda *a, **k: [{"start": 1, "end": 4, "text": "hello", "speaker": "S0"}])
    vtt = tmp_path / "a.vtt"
    vtt.write_text(VTT)
    segs, engine = tr.transcribe(tmp_path / "a.mp4", vtt, [], "key", tmp_path)
    assert engine == "sarvam+zoom" and segs[0]["speaker"] == "Kajari Kamal"


def test_transcribe_falls_back_to_zoom(monkeypatch, tmp_path: Path) -> None:
    _stub_media(monkeypatch, tmp_path)

    def boom(*a, **k):
        raise RuntimeError("sarvam down")

    monkeypatch.setattr(tr, "sarvam_transcribe", boom)
    vtt = tmp_path / "a.vtt"
    vtt.write_text(VTT)
    segs, engine = tr.transcribe(tmp_path / "a.mp4", vtt, [], "key", tmp_path)
    assert engine == "zoom" and len(segs) == 3


def test_transcribe_with_neither_raises(monkeypatch, tmp_path: Path) -> None:
    _stub_media(monkeypatch, tmp_path)
    with pytest.raises(tr.TranscribeError):
        tr.transcribe(tmp_path / "a.mp4", None, [], None, tmp_path)


def test_sarvam_failed_job_or_missing_part_raises(tmp_path: Path) -> None:
    client = FakeClient({"chunk_000.mp3": {"transcript": ""}})
    client.job.state = "Failed"
    with pytest.raises(tr.TranscribeError):
        tr.sarvam_transcribe([(tmp_path / "chunk_000.mp3", 0.0)], [], "key", client=client, work=tmp_path)
    client = FakeClient({})  # job "completed" but one part has no output
    with pytest.raises(tr.TranscribeError):
        tr.sarvam_transcribe([(tmp_path / "chunk_000.mp3", 0.0)], [], "key", client=client, work=tmp_path)
