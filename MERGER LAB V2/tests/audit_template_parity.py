#!/usr/bin/env python3
"""Assert that included/excluded templates differ only in section 03."""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "analysis_template.hwpx",
    ROOT / "analysis_template_pronunciation.hwpx",
]
NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "opf": "http://www.idpf.org/2007/opf/",
}


def canonical(element) -> bytes:
    return etree.tostring(element, method="c14n")


def main() -> int:
    archives = [zipfile.ZipFile(path) for path in FILES]
    sections = [etree.fromstring(archive.read("Contents/section0.xml")) for archive in archives]
    tables = [section.xpath(".//hp:tbl", namespaces=NS) for section in sections]
    if [len(group) for group in tables] != [6, 6]:
        raise AssertionError(f"템플릿 표 개수가 다릅니다: {[len(group) for group in tables]}")

    # 03 is table index 4. Every other numbered section must be byte-equivalent XML.
    for table_index in (0, 1, 2, 3, 5):
        if canonical(tables[0][table_index]) != canonical(tables[1][table_index]):
            raise AssertionError(f"03 이외 표가 다릅니다: table index {table_index}")

    for archive, section in zip(archives, sections):
        if archive.testzip() is not None:
            raise AssertionError(f"ZIP CRC 오류: {archive.filename}")
        references = [
            image.get("binaryItemIDRef")
            for image in section.xpath(".//hc:img", namespaces=NS)
        ]
        if references.count("logic_placeholder") != 1:
            raise AssertionError(
                f"05 자리표시자 참조 개수가 잘못되었습니다: {archive.filename} {references}"
            )

    shared_members = sorted(set(archives[0].namelist()) & set(archives[1].namelist()))
    allowed_differences = {"Contents/header.xml", "Contents/section0.xml"}
    unexpected = []
    for member in shared_members:
        if member in allowed_differences:
            continue
        if archives[0].read(member) != archives[1].read(member):
            unexpected.append(member)
    if unexpected:
        raise AssertionError(f"03 외 패키지 파일이 다릅니다: {unexpected}")

    placeholder_hashes = [
        hashlib.sha256(archive.read("BinData/logic_placeholder.png")).hexdigest()
        for archive in archives
    ]
    if len(set(placeholder_hashes)) != 1:
        raise AssertionError("05 자리표시자 이미지가 두 템플릿에서 다릅니다.")

    print("PASS: 00·01·02·04·05 표 XML 동일")
    print("PASS: 05 자리표시자 이미지 동일")
    print("PASS: 허용 차이는 03 표와 그 발음 서식(header.xml)뿐")
    return 0


if __name__ == "__main__":
    sys.exit(main())
