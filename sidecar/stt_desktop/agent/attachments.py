"""Bounded local attachment parsing, using the web's official workbook contracts."""

import io
import json
import zipfile
from pathlib import Path

from stt_desktop.storage import ProjectError
from stt_desktop.storage.project import uuid7
from stt_desktop.agent.upstream.file_parser import parse_attachment_content


def store_attachment(service, scene, filename, data):
    if scene not in {"rooms", "school", "planning", "timetable", "constraints"}:
        raise ProjectError("无效的附件场景")
    filename = Path(filename).name
    if len(data) > 2 * 1024 * 1024:
        raise ProjectError("附件不能超过2 MB")
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".docx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if (
                    len(archive.infolist()) > 1000
                    or sum(i.file_size for i in archive.infolist()) > 40 * 1024 * 1024
                ):
                    raise ProjectError("附件解压后过大，请拆分")
                if any("externalLinks/" in i.filename for i in archive.infolist()):
                    raise ProjectError("请移除附件中的外部链接")
        except zipfile.BadZipFile as exc:
            raise ProjectError("附件不是有效的Office文件") from exc
    parsed = parse_attachment_content(
        filename if suffix not in {".md", ".json"} else filename + ".txt", data, 2
    )
    if len(json.dumps(parsed, ensure_ascii=False).encode()) > 700_000:
        raise ProjectError("解析后的附件过大，请拆分；未截取部分内容导入")
    attachment = {
        "id": uuid7(),
        "flow": "attachment",
        "scene": scene,
        "filename": filename,
        "extracted_text": parsed["text"],
        "extracted_data": parsed["data"],
    }
    service.put("turn", scene, attachment)
    return {
        "id": attachment["id"],
        "filename": filename,
        "text": parsed["text"],
        "localParsed": True,
    }


def load_attachments(service, scene, identifiers):
    if len(identifiers) > 5 or len(set(identifiers)) != len(identifiers):
        raise ProjectError("每次最多5个不同附件")
    result = []
    for identifier in identifiers:
        attachment = service.get("turn", identifier)
        if attachment.get("flow") != "attachment" or attachment.get("scene") != scene:
            raise ProjectError("附件不属于当前项目或场景，请重新选择")
        result.append(attachment)
    return result
