#!/usr/bin/env python3
"""Insert and validate V2 logic-diagram image resources in HWPX packages."""

from __future__ import annotations

import copy
import io
import shutil
import zipfile
from pathlib import Path

from lxml import etree


HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HC_NS = "http://www.hancom.co.kr/hwpml/2011/core"
OPF_NS = "http://www.idpf.org/2007/opf/"
NS = {"hp": HP_NS, "hc": HC_NS, "opf": OPF_NS}

PLACEHOLDER_RESOURCE_ID = "logic_placeholder"
LOGIC_HEADING = "05 · 지문 논리 한눈에 보기"
LOGIC_IMAGE_WIDTH = 48135
LOGIC_IMAGE_HEIGHT = 28500


def hp(tag: str) -> str:
    return f"{{{HP_NS}}}{tag}"


def hc(tag: str) -> str:
    return f"{{{HC_NS}}}{tag}"


def _element_text(element) -> str:
    return "".join((node.text or "") for node in element.findall(".//hp:t", NS)).strip()


def _contains_logic_picture(element) -> bool:
    return any(
        image.get("binaryItemIDRef") == PLACEHOLDER_RESOURCE_ID
        for image in element.findall(".//hc:img", NS)
    )


def remove_logic_elements(elements):
    """Return a block containing only the legacy 00~04 elements."""
    return [
        element for element in elements
        if not _element_text(element).startswith("05 ·") and not _contains_logic_picture(element)
    ]


def find_logic_picture(elements):
    pictures = []
    for element in elements:
        for picture in element.findall(".//hp:pic", NS):
            image = picture.find("./hc:img", NS)
            if image is not None and image.get("binaryItemIDRef") == PLACEHOLDER_RESOURCE_ID:
                pictures.append(picture)
    if len(pictures) != 1:
        raise ValueError(f"V2 템플릿의 논리 시각화 자리표시자는 1개여야 합니다. actual={len(pictures)}")
    return pictures[0]


def replace_logic_picture(elements, resource_id: str, passage_index: int):
    picture = find_logic_picture(elements)
    image = picture.find("./hc:img", NS)
    image.set("binaryItemIDRef", resource_id)
    picture.set("id", str(1800000000 + passage_index * 2))
    picture.set("instid", str(1800000001 + passage_index * 2))
    picture.set("zOrder", str(40 + passage_index))
    comment = picture.find("./hp:shapeComment", NS)
    if comment is not None:
        comment.text = f"MERGER LAB V2 논리 시각화 이미지 {passage_index + 1}"


def _write_xml(tree, path: Path):
    tree.write(str(path), xml_declaration=True, encoding="UTF-8", standalone=True)


def add_png_resource(package_dir: Path, resource_id: str, png_path: Path):
    content_path = package_dir / "Contents" / "content.hpf"
    tree = etree.parse(str(content_path))
    manifest = tree.getroot().find("./opf:manifest", NS)
    if manifest is None:
        raise ValueError("HWPX Contents/content.hpf에 manifest가 없습니다.")
    if manifest.find(f"./opf:item[@id='{resource_id}']", NS) is not None:
        raise ValueError(f"HWPX 이미지 리소스 ID가 중복되었습니다: {resource_id}")

    href = f"BinData/{resource_id}.png"
    item = etree.Element(f"{{{OPF_NS}}}item")
    item.set("id", resource_id)
    item.set("href", href)
    item.set("media-type", "image/png")
    item.set("isEmbeded", "1")
    manifest.append(item)

    target = package_dir / href
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(png_path, target)
    _write_xml(tree, content_path)


def remove_placeholder_resource(package_dir: Path):
    content_path = package_dir / "Contents" / "content.hpf"
    tree = etree.parse(str(content_path))
    manifest = tree.getroot().find("./opf:manifest", NS)
    if manifest is not None:
        item = manifest.find(f"./opf:item[@id='{PLACEHOLDER_RESOURCE_ID}']", NS)
        if item is not None:
            manifest.remove(item)
    placeholder = package_dir / "BinData" / f"{PLACEHOLDER_RESOURCE_ID}.png"
    placeholder.unlink(missing_ok=True)
    _write_xml(tree, content_path)


def _make_picture_from_template(template_picture, resource_id=PLACEHOLDER_RESOURCE_ID):
    picture = copy.deepcopy(template_picture)
    picture.set("id", "1800000000")
    picture.set("instid", "1800000001")
    picture.set("zOrder", "40")
    picture.set("textWrap", "TOP_AND_BOTTOM")
    picture.set("textFlow", "BOTH_SIDES")
    picture.set("lock", "0")

    offset = picture.find("./hp:offset", NS)
    if offset is not None:
        offset.set("x", "0")
        offset.set("y", "0")

    original_width, original_height = 120000, 71250
    for tag in ("orgSz", "curSz"):
        node = picture.find(f"./hp:{tag}", NS)
        if node is not None:
            node.set("width", str(original_width if tag == "orgSz" else LOGIC_IMAGE_WIDTH))
            node.set("height", str(original_height if tag == "orgSz" else LOGIC_IMAGE_HEIGHT))

    rotation = picture.find("./hp:rotationInfo", NS)
    if rotation is not None:
        rotation.set("angle", "0")
        rotation.set("centerX", str(LOGIC_IMAGE_WIDTH // 2))
        rotation.set("centerY", str(LOGIC_IMAGE_HEIGHT // 2))
        rotation.set("rotateimage", "1")

    rendering = picture.find("./hp:renderingInfo", NS)
    if rendering is not None:
        for child in list(rendering):
            local = etree.QName(child).localname
            if local in {"transMatrix", "rotMatrix"}:
                child.attrib.update({"e1": "1", "e2": "0", "e3": "0", "e4": "0", "e5": "1", "e6": "0"})
            elif local == "scaMatrix":
                child.attrib.update({
                    "e1": f"{LOGIC_IMAGE_WIDTH / original_width:.6f}", "e2": "0", "e3": "0", "e4": "0",
                    "e5": f"{LOGIC_IMAGE_HEIGHT / original_height:.6f}", "e6": "0",
                })

    image = picture.find("./hc:img", NS)
    if image is None:
        image = etree.SubElement(picture, hc("img"))
    image.attrib.update({
        "binaryItemIDRef": resource_id,
        "bright": "0", "contrast": "0", "effect": "REAL_PIC", "alpha": "0",
    })

    image_rect = picture.find("./hp:imgRect", NS)
    if image_rect is not None:
        points = [
            ("pt0", 0, 0),
            ("pt1", original_width, 0),
            ("pt2", original_width, original_height),
            ("pt3", 0, original_height),
        ]
        for tag, x, y in points:
            point = image_rect.find(f"./hc:{tag}", NS)
            if point is not None:
                point.set("x", str(x))
                point.set("y", str(y))

    clip = picture.find("./hp:imgClip", NS)
    if clip is not None:
        clip.attrib.update({"left": "0", "right": str(original_width), "top": "0", "bottom": str(original_height)})
    dimensions = picture.find("./hp:imgDim", NS)
    if dimensions is not None:
        dimensions.attrib.update({"dimwidth": str(original_width), "dimheight": str(original_height)})
    size = picture.find("./hp:sz", NS)
    if size is not None:
        size.attrib.update({
            "width": str(LOGIC_IMAGE_WIDTH), "widthRelTo": "ABSOLUTE",
            "height": str(LOGIC_IMAGE_HEIGHT), "heightRelTo": "ABSOLUTE", "protect": "0",
        })
    position = picture.find("./hp:pos", NS)
    if position is not None:
        position.attrib.update({
            "treatAsChar": "0", "affectLSpacing": "0", "flowWithText": "1",
            "allowOverlap": "0", "holdAnchorAndSO": "0", "vertRelTo": "PARA",
            "horzRelTo": "COLUMN", "vertAlign": "TOP", "horzAlign": "LEFT",
            "vertOffset": "0", "horzOffset": "0",
        })
    comment = picture.find("./hp:shapeComment", NS)
    if comment is not None:
        comment.text = "MERGER LAB V2 논리 시각화 자리표시자"
    return picture


def make_logic_picture_paragraph(base_paragraph, template_picture):
    paragraph = copy.deepcopy(base_paragraph)
    paragraph.attrib.update({
        "id": "0", "paraPrIDRef": "15", "styleIDRef": "6",
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    for child in list(paragraph):
        paragraph.remove(child)
    run = etree.SubElement(paragraph, hp("run"))
    run.set("charPrIDRef", "9")
    run.append(_make_picture_from_template(template_picture))
    etree.SubElement(run, hp("t"))
    return paragraph


def add_placeholder_resource(package_dir: Path, png_path: Path):
    content_path = package_dir / "Contents" / "content.hpf"
    tree = etree.parse(str(content_path))
    manifest = tree.getroot().find("./opf:manifest", NS)
    if manifest is None:
        raise ValueError("HWPX Contents/content.hpf에 manifest가 없습니다.")
    old = manifest.find(f"./opf:item[@id='{PLACEHOLDER_RESOURCE_ID}']", NS)
    if old is not None:
        manifest.remove(old)
    item = etree.Element(f"{{{OPF_NS}}}item")
    item.set("id", PLACEHOLDER_RESOURCE_ID)
    item.set("href", f"BinData/{PLACEHOLDER_RESOURCE_ID}.png")
    item.set("media-type", "image/png")
    item.set("isEmbeded", "1")
    manifest.append(item)
    target = package_dir / "BinData" / f"{PLACEHOLDER_RESOURCE_ID}.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(png_path, target)
    _write_xml(tree, content_path)


def validate_hwpx_image_references(hwpx_source) -> dict:
    """Return a machine-readable reference report; accepts a path or bytes."""
    stream = io.BytesIO(hwpx_source) if isinstance(hwpx_source, (bytes, bytearray)) else hwpx_source
    errors = []
    with zipfile.ZipFile(stream) as archive:
        names = set(archive.namelist())
        package = etree.fromstring(archive.read("Contents/content.hpf"))
        manifest_items = package.findall("./opf:manifest/opf:item", NS)
        resources = {item.get("id"): item.get("href") for item in manifest_items}
        references = []
        logic_references = []
        for section_name in sorted(name for name in names if name.startswith("Contents/section") and name.endswith(".xml")):
            section = etree.fromstring(archive.read(section_name))
            for image in section.findall(".//hc:img", NS):
                resource_id = image.get("binaryItemIDRef")
                references.append(resource_id)
                if resource_id and resource_id.startswith("logic_"):
                    logic_references.append(resource_id)
                if resource_id not in resources:
                    errors.append(f"{section_name}: manifest에 없는 이미지 참조 {resource_id}")
                    continue
                href = resources[resource_id]
                if href not in names:
                    errors.append(f"{section_name}: 패키지에 없는 이미지 파일 {href}")
        if len(logic_references) != len(set(logic_references)):
            errors.append("다중 지문의 논리 이미지 리소스 ID가 중복되었습니다.")
        if PLACEHOLDER_RESOURCE_ID in references:
            errors.append("출력 HWPX에 논리 이미지 자리표시자 참조가 남았습니다.")
        bad_items = [resource_id for resource_id, href in resources.items() if href and href.startswith("BinData/") and href not in names]
        for resource_id in bad_items:
            errors.append(f"manifest 리소스 파일이 없습니다: {resource_id} -> {resources[resource_id]}")
        bad_zip_member = archive.testzip()
        if bad_zip_member:
            errors.append(f"ZIP CRC 오류: {bad_zip_member}")
    return {
        "ok": not errors,
        "errors": errors,
        "image_references": references,
        "logic_image_references": logic_references,
        "resources": resources,
    }


__all__ = [
    "LOGIC_HEADING",
    "PLACEHOLDER_RESOURCE_ID",
    "add_placeholder_resource",
    "add_png_resource",
    "find_logic_picture",
    "make_logic_picture_paragraph",
    "remove_logic_elements",
    "remove_placeholder_resource",
    "replace_logic_picture",
    "validate_hwpx_image_references",
]
