#!/usr/bin/env python3
"""Add the 05 heading and logic-image placeholder to both copied V2 templates."""

from __future__ import annotations

import copy
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image, ImageDraw, ImageFont

from hwpx_logic_embedder import (
    LOGIC_HEADING,
    NS,
    add_placeholder_resource,
    make_logic_picture_paragraph,
)


ROOT = Path(__file__).resolve().parent
TEMPLATES = [ROOT / "analysis_template.hwpx", ROOT / "analysis_template_pronunciation.hwpx"]


def element_text(element):
    return "".join((node.text or "") for node in element.findall(".//hp:t", NS)).strip()


def is_empty_paragraph(element):
    return (
        etree.QName(element).localname == "p"
        and not element_text(element)
        and not element.findall(".//hp:tbl", NS)
        and not element.findall(".//hp:pic", NS)
        and not element.findall(".//hp:ctrl", NS)
    )


def make_placeholder(path: Path):
    image = Image.new("RGB", (1800, 1060), "#FBF8F1")
    draw = ImageDraw.Draw(image)
    regular = Path(r"C:\Windows\Fonts\malgun.ttf")
    bold = Path(r"C:\Windows\Fonts\malgunbd.ttf")
    font = ImageFont.truetype(str(bold if bold.exists() else regular), 46)
    small = ImageFont.truetype(str(regular), 30)
    draw.rounded_rectangle((80, 80, 1720, 980), radius=36, fill="#F3F7F2", outline="#426B5C", width=4)
    label = "논리 시각화 자리표시자"
    note = "실제 출력에서는 승인 JSON의 도식 이미지로 교체됩니다."
    box = draw.textbbox((0, 0), label, font=font)
    draw.text(((1800 - (box[2] - box[0])) / 2, 450), label, font=font, fill="#23594B")
    box = draw.textbbox((0, 0), note, font=small)
    draw.text(((1800 - (box[2] - box[0])) / 2, 535), note, font=small, fill="#5E675F")
    image.save(path, format="PNG", optimize=True, dpi=(220, 220))


def rebuild_archive(extracted: Path, destination: Path):
    temp_output = destination.with_suffix(".hwpx.tmp")
    with zipfile.ZipFile(temp_output, "w", zipfile.ZIP_DEFLATED) as archive:
        mimetype = extracted / "mimetype"
        archive.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
        for dirpath, _, filenames in os.walk(extracted):
            for filename in filenames:
                source = Path(dirpath) / filename
                relative = source.relative_to(extracted)
                if relative.as_posix() == "mimetype":
                    continue
                archive.write(source, relative.as_posix())
    temp_output.replace(destination)


def build_template(template_path: Path):
    with tempfile.TemporaryDirectory(prefix="merger_lab_v2_template_") as temp_dir:
        extracted = Path(temp_dir)
        with zipfile.ZipFile(template_path) as archive:
            archive.extractall(extracted)

        section_path = extracted / "Contents" / "section0.xml"
        tree = etree.parse(str(section_path))
        root = tree.getroot()
        children = list(root)
        heading_index = next(
            index for index, element in enumerate(children)
            if element_text(element).startswith("04 ·")
        )
        vocab_index = next(
            index for index in range(heading_index + 1, len(children))
            if children[index].find(".//hp:tbl", NS) is not None
        )
        template_picture = root.find(".//hp:pic", NS)
        if template_picture is None:
            raise ValueError(f"그림 객체 복제 기준이 없습니다: {template_path.name}")

        base_paragraph = next(
            (element for element in children[vocab_index + 1:] if is_empty_paragraph(element)),
            children[heading_index],
        )
        for element in children[vocab_index + 1:]:
            if is_empty_paragraph(element):
                root.remove(element)

        heading = copy.deepcopy(children[heading_index])
        heading.set("pageBreak", "0")
        text_nodes = heading.findall(".//hp:t", NS)
        if not text_nodes:
            raise ValueError(f"04 제목 텍스트를 찾지 못했습니다: {template_path.name}")
        text_nodes[0].text = LOGIC_HEADING
        for extra in text_nodes[1:]:
            extra.text = ""
        picture_paragraph = make_logic_picture_paragraph(base_paragraph, template_picture)
        root.insert(vocab_index + 1, heading)
        root.insert(vocab_index + 2, picture_paragraph)

        tree.write(str(section_path), xml_declaration=True, encoding="UTF-8", standalone=True)
        placeholder = extracted / "logic_placeholder.png"
        make_placeholder(placeholder)
        add_placeholder_resource(extracted, placeholder)
        placeholder.unlink()
        rebuild_archive(extracted, template_path)


def main():
    for template in TEMPLATES:
        if not template.is_file():
            raise FileNotFoundError(template)
        build_template(template)
        print(f"완료: {template.name}")


if __name__ == "__main__":
    main()
