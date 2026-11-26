#!/usr/bin/env python3
"""학술대회 논문 양식(template.hwpx)에 JSON 내용을 채워 새 .hwpx 를 만든다.

사용법:
  python make_paper.py paper.json output.hwpx

paper.json 스키마는 SKILL.md 참고. 전역 hwpx 스킬(~/.claude/skills/hwpx)의
fill_hwpx.py 를 재사용한다 (하이퍼링크 글자 스타일, 쪽번호 삽입).
"""
import io
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "template.hwpx"
HWPX_SCRIPTS = Path.home() / ".claude" / "skills" / "hwpx" / "scripts"
sys.path.insert(0, str(HWPX_SCRIPTS))
import fill_hwpx as fh  # noqa: E402

ROMAN = ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ", "Ⅴ", "Ⅵ", "Ⅶ", "Ⅷ", "Ⅸ", "Ⅹ"]
URL_RE = re.compile(r"https?://[^\s,;)]+[^\s,;).]")
PARA_RE = re.compile(r"<hp:p .*?</hp:p>", re.S)
SEG_RE = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.S)
T_RE = re.compile(r"<hp:t>.*?</hp:t>", re.S)


def ptext(p):
    return "".join(re.findall(r"<hp:t>(.*?)</hp:t>", p, re.S))


def with_text(p, text):
    p = SEG_RE.sub("", p)
    return T_RE.sub(lambda m: "<hp:t>%s</hp:t>" % fh.escape_text(text), p, count=1)


def with_runs(p, runs_xml):
    """문단의 첫 run 을 runs_xml 로 교체 (링크 포함 문단용)."""
    p = SEG_RE.sub("", p)
    return re.sub(r"<hp:run .*?</hp:run>", lambda m: runs_xml, p, count=1, flags=re.S)


def split_top(sec):
    """최상위 <hp:p> 의 (시작, 끝) 위치. 표/글상자 안의 중첩 단락은 건너뛴다."""
    depth, spans, start = 0, [], 0
    for m in re.finditer(r"<hp:p |</hp:p>", sec):
        if m.group() == "<hp:p ":
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
    return spans


def fill_front(p0, spec):
    """첫 단락(제목 표·저자 각주 표)의 자리표시자를 제자리에서 치환한다."""
    notes = spec.get("notes", [])
    kw = ", ".join(spec["keywords"])
    table = [
        ("{{소속1}}", None), ("{{소속2}}", None),
        ("{{국문 제목}}", spec["title_ko"]), ("{{저자1}}", spec["authors_ko"]),
        ("{{English Title}}", spec["title_en"]), ("{{Author1}}", spec["authors_en"]),
        ("{{국문 요약}}", spec["abstract"]), ("{{Keyword1", kw),
    ]

    def rep(m):
        t = m.group(1)
        for key, val in table:
            if t.lstrip().startswith(key) or (key.startswith("{{소속") and key in t):
                if key == "{{소속1}}":
                    val = ("  * " + notes[0]) if len(notes) > 0 else ""
                elif key == "{{소속2}}":
                    val = (" ** " + notes[1]) if len(notes) > 1 else ""
                return "<hp:t>%s</hp:t>" % fh.escape_text(val)
        return m.group()
    return re.sub(r"<hp:t>(.*?)</hp:t>", rep, p0, flags=re.S)


def build(spec, out_path):
    z = zipfile.ZipFile(TEMPLATE)
    sec = z.read("Contents/section0.xml").decode("utf8")
    header_name = "Contents/header.xml"
    header = z.read(header_name).decode("utf8")
    spans = split_top(sec)
    pre, post = sec[:spans[0][0]], sec[spans[-1][1]:]
    ps = [sec[a:b] for a, b in spans]

    def find(prefix):
        return next(p for p in ps[1:] if ptext(p).startswith(prefix))

    blank = SEG_RE.sub("", ps[1])
    h1, h2 = find("Ⅰ."), find("1.1")
    body = find("{{본문 단락}}")
    ref = find("{{참고문헌")
    label_ref = ps[ps.index(ref) - 2]
    link_cid, header = _link_style(header, ref)

    out = [fill_front(ps[0], spec), blank]

    for n, s in enumerate(spec["sections"]):
        if n > 0:
            out += [blank, blank]
        out += [with_text(h1, "%s. %s" % (ROMAN[n], s["heading"])), blank]
        for para in s.get("paragraphs", []):
            out.append(with_text(body, para))
        for m, sub in enumerate(s.get("subsections", []), 1):
            out += [with_text(h2, "%d.%d %s" % (n + 1, m, sub["heading"])), blank]
            for para in sub.get("paragraphs", []):
                out.append(with_text(body, para))

    out += [blank, blank, SEG_RE.sub("", label_ref), blank]
    uid = [5000]
    cid = re.search(r'charPrIDRef="(\d+)"', ref).group(1)
    for r in spec["references"]:
        out.append(with_runs(ref, _ref_runs(r, cid, link_cid, uid)))

    new_sec = pre + "".join(out) + post
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zo:
        for item in z.infolist():
            d = z.read(item.filename)
            if item.filename == "Contents/section0.xml":
                d = new_sec.encode("utf8")
            elif item.filename == header_name:
                d = header.encode("utf8")
            elif item.filename == "Preview/PrvText.txt":
                d = spec["title_ko"].encode("utf8")
            zo.writestr(item.filename, d, compress_type=(
                zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED))
    tmp = Path(str(out_path) + ".tmp")
    tmp.write_bytes(buf.getvalue())
    # 쪽번호(하단 가운데) 삽입
    fh.set_pagenum_hwpx(str(tmp), str(out_path), where="footer", align="CENTER")
    tmp.unlink()


def _link_style(header, ref_para):
    base = re.search(r'charPrIDRef="(\d+)"', ref_para).group(1)
    new_cid, new_header = fh._add_cloned(
        header, "charProperties", "charPr", base,
        fh._mutate_charpr(False, False, True, "0000FF", None))
    return new_cid, new_header


def _ref_runs(text, cid, link_cid, uid):
    runs, pos = [], 0
    for m in URL_RE.finditer(text):
        if m.start() > pos:
            runs.append('<hp:run charPrIDRef="%s"><hp:t>%s</hp:t></hp:run>'
                        % (cid, fh.escape_text(text[pos:m.start()])))
        uid[0] += 2
        runs.append(fh._hyperlink_run_xml(link_cid, uid[0], uid[0] + 1, m.group(), m.group()))
        pos = m.end()
    if pos < len(text):
        runs.append('<hp:run charPrIDRef="%s"><hp:t>%s</hp:t></hp:run>'
                    % (cid, fh.escape_text(text[pos:])))
    return "".join(runs)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: make_paper.py paper.json output.hwpx")
    build(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2]))
    print("saved", sys.argv[2])
