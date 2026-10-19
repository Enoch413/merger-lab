#!/usr/bin/env python3
"""Promote the user-edited T01 output to the reusable V2 base template."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

from hwpx_logic_embedder import (
    HC_NS,
    HP_NS,
    LOGIC_IMAGE_HEIGHT,
    LOGIC_IMAGE_WIDTH,
    PLACEHOLDER_RESOURCE_ID,
)


NS = {
    "hp": HP_NS,
    "hc": HC_NS,
    "opf": "http://www.idpf.org/2007/opf/",
}


def rebuild_archive(extracted: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".new")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(extracted / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
        for dirpath, _, filenames in os.walk(extracted):
            for filename in filenames:
                source = Path(dirpath) / filename
                relative = source.relative_to(extracted).as_posix()
                if relative == "mimetype":
                    continue
                archive.write(source, relative)
    temporary.replace(destination)


def find_logic_picture(section):
    candidates = []
    for picture in section.findall(".//hp:pic", NS):
        size = picture.find("./hp:curSz", NS)
        image = picture.find("./hc:img", NS)
        if size is None or image is None:
            continue
        if (
            size.get("width") == str(LOGIC_IMAGE_WIDTH)
            and size.get("height") == str(LOGIC_IMAGE_HEIGHT)
        ):
            candidates.append((picture, image))
    if len(candidates) != 1:
        raise ValueError(
            "T01 출력에서 05 논리 시각화 그림을 하나로 식별하지 못했습니다. "
            f"actual={len(candidates)}"
        )
    return candidates[0]


def promote(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)

    with tempfile.TemporaryDirectory(prefix="merger_lab_promote_t01_") as temp_dir:
        extracted = Path(temp_dir)
        with zipfile.ZipFile(source) as archive:
            archive.extractall(extracted)

        section_path = extracted / "Contents" / "section0.xml"
        content_path = extracted / "Contents" / "content.hpf"
        section_tree = etree.parse(str(section_path))
        content_tree = etree.parse(str(content_path))
        picture, image = find_logic_picture(section_tree.getroot())

        source_id = image.get("binaryItemIDRef")
        if not source_id:
            raise ValueError("05 논리 시각화 그림의 이미지 리소스 ID가 없습니다.")
        manifest = content_tree.getroot().find("./opf:manifest", NS)
        if manifest is None:
            raise ValueError("HWPX manifest를 찾지 못했습니다.")
        source_item = manifest.find(f"./opf:item[@id='{source_id}']", NS)
        if source_item is None:
            raise ValueError(f"05 그림 리소스가 manifest에 없습니다: {source_id}")
        if manifest.find(f"./opf:item[@id='{PLACEHOLDER_RESOURCE_ID}']", NS) is not None:
            raise ValueError("입력 T01에 기존 논리 자리표시자 리소스가 남아 있습니다.")

        source_href = source_item.get("href")
        if not source_href:
            raise ValueError(f"05 그림 리소스 경로가 없습니다: {source_id}")
        source_binary = extracted / source_href
        if not source_binary.is_file():
            raise FileNotFoundError(source_binary)

        placeholder_href = f"BinData/{PLACEHOLDER_RESOURCE_ID}.png"
        placeholder_binary = extracted / placeholder_href
        placeholder_binary.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_binary, placeholder_binary)
        if source_binary.resolve() != placeholder_binary.resolve():
            source_binary.unlink()

        image.set("binaryItemIDRef", PLACEHOLDER_RESOURCE_ID)
        picture.set("id", "1800000000")
        picture.set("instid", "1800000001")
        comment = picture.find("./hp:shapeComment", NS)
        if comment is not None:
            comment.text = "MERGER LAB V2 논리 시각화 자리표시자"
        source_item.set("id", PLACEHOLDER_RESOURCE_ID)
        source_item.set("href", placeholder_href)
        source_item.set("media-type", "image/png")
        source_item.set("isEmbeded", "1")

        section_tree.write(
            str(section_path), xml_declaration=True, encoding="UTF-8", standalone=True
        )
        content_tree.write(
            str(content_path), xml_declaration=True, encoding="UTF-8", standalone=True
        )
        rebuild_archive(extracted, destination)

    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise ValueError("교체한 템플릿 ZIP CRC 검증에 실패했습니다.")
        if f"BinData/{PLACEHOLDER_RESOURCE_ID}.png" not in archive.namelist():
            raise ValueError("교체한 템플릿에 논리 자리표시자 이미지가 없습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    promote(args.source.resolve(), args.destination.resolve())
    print(args.destination.resolve())


if __name__ == "__main__":
    main()
