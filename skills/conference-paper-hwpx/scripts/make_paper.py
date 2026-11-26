#!/usr/bin/env python3
"""학술대회 논문 양식(template.hwpx)에 JSON 내용을 채워 새 .hwpx 를 만든다.

사용법:  python make_paper.py paper.json output.hwpx

paper.json 스키마는 SKILL.md 참고. 전역 hwpx 스킬(~/.claude/skills/hwpx)의
fill_hwpx.py 를 재사용한다 (하이퍼링크 글자 스타일, 이미지 삽입).
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
SEG_RE = re.compile(r"<hp:linesegarray>.*?</hp:linesegarray>", re.S)
T_RE = re.compile(r"<hp:t>.*?</hp:t>", re.S)
COLPR_RE = re.compile(r"<hp:ctrl><hp:colPr [^>]*colCount=\"2\"[^>]*/></hp:ctrl>")
COL_W = 20124            # 2단 조판에서 한 단의 폭 (HWPUNIT)
FIG_MM = 65              # 그림 기본 폭 (한 단 폭 71mm 안쪽)
CENTER, LEFT = "2", "10"  # 문단모양 id (가운데 100% / 좌측 130%)


# ───────────────────────── XML 조각 만들기 ─────────────────────────
def esc(t):
    return fh.escape_text(t)


def run(text, cid):
    return '<hp:run charPrIDRef="%s"><hp:t>%s</hp:t></hp:run>' % (cid, esc(text))


def para(ppr, style, runs):
    return ('<hp:p id="0" paraPrIDRef="%s" styleIDRef="%s" pageBreak="0" '
            'columnBreak="0" merged="0">%s</hp:p>' % (ppr, style, runs))


def footnote_run(text, no=1, marker=False):
    """각주(첫 쪽 하단, 구분선은 양식의 noteLine 설정). 번호는 한글이 자동 부여."""
    head = ('<hp:run charPrIDRef="0"><hp:ctrl>'
            '<hp:footNote number="%d" suffixChar="%s" instId="%d">'
            % (no, "" if marker else ")", 7000 + no))
    return (head
            + '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
              'vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0" '
              'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            + para(LEFT, "13", run(("" if marker else " ") + text, "11")
                   + '<hp:linesegarray><hp:lineseg textpos="0" vertpos="%d" vertsize="1000" '
                     'textheight="1000" baseline="850" spacing="300" horzpos="0" '
                     'horzsize="%d" flags="393216"/></hp:linesegarray>'
                   % ((no - 1) * 1300, 42520))
            + '</hp:subList></hp:footNote></hp:ctrl></hp:run>')


def authors_runs(names, notes, cid, marker=False):
    """저자 줄. notes[i] 가 있으면 i번째 저자 뒤에 각주를 단다."""
    runs, buf = [], ""
    for i, name in enumerate(names):
        buf += (", " if i else "") + name
        if i < len(notes) and notes[i]:
            runs.append(run(buf, cid))
            buf = ""
            runs.append(footnote_run(notes[i], i + 1, marker))
    if buf:
        runs.append(run(buf, cid))
    return "".join(runs)


def caption(kind, no, text):
    """표/그림 캡션. 스타일: 학술-표캡션(15) / 학술-그림캡션(14)."""
    label = "표" if kind == "table" else "그림"
    style, cid = ("15", "2") if kind == "table" else ("14", "0")
    return para(CENTER, style, run("%s %d. %s" % (label, no, text), cid))


def table_xml(rows, uid, header=True):
    """한 단 폭에 맞는 격자 표 (글자처럼 취급)."""
    ncol, nrow = len(rows[0]), len(rows)
    cw, rh = COL_W // ncol, 1500
    out = ['<hp:tbl id="%d" zOrder="0" numberingType="TABLE" '
           'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" '
           'dropcapstyle="None" pageBreak="CELL" repeatHeader="0" rowCnt="%d" '
           'colCnt="%d" cellSpacing="0" borderFillIDRef="4" noAdjust="0">'
           '<hp:sz width="%d" widthRelTo="ABSOLUTE" height="%d" '
           'heightRelTo="ABSOLUTE" protect="0"/>'
           '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" '
           'allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" '
           'horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER" '
           'vertOffset="0" horzOffset="0"/>'
           '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
           '<hp:inMargin left="140" right="140" top="0" bottom="0"/>'
           % (uid(), nrow, ncol, cw * ncol, rh * nrow)]
    for r, row in enumerate(rows):
        out.append("<hp:tr>")
        for c, cell in enumerate(row):
            out.append(
                '<hp:tc name="" header="%d" hasMargin="0" protect="0" '
                'editable="0" dirty="0" borderFillIDRef="4">'
                '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
                'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
                'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">%s'
                '</hp:subList><hp:cellAddr colAddr="%d" rowAddr="%d"/>'
                '<hp:cellSpan colSpan="1" rowSpan="1"/>'
                '<hp:cellSz width="%d" height="%d"/>'
                '<hp:cellMargin left="141" right="141" top="141" bottom="141"/>'
                '</hp:tc>'
                % (1 if (header and r == 0) else 0,
                   para(CENTER, "0", run(str(cell), "3")), c, r, cw, rh))
        out.append("</hp:tr>")
    out.append("</hp:tbl>")
    return "".join(out)


def table_para(rows, uid, header=True):
    return para(CENTER, "0", '<hp:run charPrIDRef="0">%s<hp:t/></hp:run>'
                % table_xml(rows, uid, header))


def figure_para(token):
    """그림 자리. 토큰 문단에 이미지를 글자처럼 삽입한 뒤 토큰은 지운다."""
    return para(CENTER, "0", run(token, "0"))


# ─────────────────────────── 패키지 가공 ───────────────────────────
def rewrite_zip(zbytes, fn):
    """fn(name, data) -> data|None(삭제). mimetype 은 무압축 첫 항목으로 유지."""
    zi = zipfile.ZipFile(io.BytesIO(zbytes))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zo:
        for item in zi.infolist():
            d = fn(item.filename, zi.read(item.filename))
            if d is None:
                continue
            zo.writestr(item.filename, d, compress_type=(
                zipfile.ZIP_STORED if item.filename == "mimetype"
                else zipfile.ZIP_DEFLATED))
    return buf.getvalue()


def add_figures(path, figs):
    """figs = [(token, 이미지경로, 폭mm)]. 이미지를 삽입하고 토큰 글자를 지운다."""
    path = Path(path)
    for k, (token, img, w) in enumerate(figs):
        tmp = Path(str(path) + ".fig%d" % k)
        fh.insert_image_hwpx(str(path), str(tmp), str(img), after=token,
                             inline=True, width_mm=w)
        tmp.replace(path)

    def strip(name, d):
        if name.startswith("Contents/section"):
            s = d.decode("utf8")
            for token, _, _ in figs:
                s = s.replace(token, "")
            return s.encode("utf8")
        return d
    path.write_bytes(rewrite_zip(path.read_bytes(), strip))


def drop_bindata(name, d):
    """템플릿의 견본 그림을 버린다 (생성 시 필요한 그림만 다시 넣는다)."""
    if name.startswith("BinData/"):
        return None
    if name.endswith("content.hpf"):
        s = re.sub(r'<opf:item [^>]*href="BinData/[^"]*"[^>]*/>', "", d.decode("utf8"))
        return s.encode("utf8")
    return d


# ─────────────────────────── 문서 생성 ───────────────────────────
def ptext(p):
    return "".join(re.findall(r"<hp:t>(.*?)</hp:t>", p, re.S))


def with_text(p, text):
    p = SEG_RE.sub("", p)
    return T_RE.sub(lambda m: "<hp:t>%s</hp:t>" % esc(text), p, count=1)


def with_runs(p, runs_xml):
    p = SEG_RE.sub("", p)
    return re.sub(r"<hp:run .*?</hp:run>", lambda m: runs_xml, p, count=1, flags=re.S)


def split_top(sec):
    """최상위 <hp:p> 의 (시작, 끝). 표/글상자 안의 중첩 단락은 건너뛴다."""
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


def names_of(v):
    return v if isinstance(v, list) else [a.strip() for a in re.split(r"[,，]", v) if a.strip()]


def fill_front(p, spec):
    """앞부분 자리표시자 치환 (제목·영문저자·요약·키워드·머리말)."""
    kw = ", ".join(spec["keywords"])
    en = spec["authors_en"]
    table = [("{{국문 제목}}", spec["title_ko"]), ("{{English Title}}", spec["title_en"]),
             ("{{Author1}}", ", ".join(en) if isinstance(en, list) else en),
             ("{{국문 요약}}", spec["abstract"]), ("{{Keyword1", kw)]

    def rep(m):
        t = m.group(1)
        if t == "ㅇㅇㅇ학회 학술대회" and spec.get("society"):
            return "<hp:t>%s</hp:t>" % esc(spec["society"])
        for key, val in table:
            if t.startswith(key):
                return "<hp:t>%s</hp:t>" % esc(val)
        return m.group()
    return re.sub(r"<hp:t>(.*?)</hp:t>", rep, p, flags=re.S)


def build(spec, out_path):
    z = zipfile.ZipFile(TEMPLATE)
    sec = z.read("Contents/section0.xml").decode("utf8")
    header = z.read("Contents/header.xml").decode("utf8")
    spans = split_top(sec)
    pre, post = sec[:spans[0][0]], sec[spans[-1][1]:]
    ps = [sec[a:b] for a, b in spans]

    first_h1 = next(i for i, p in enumerate(ps) if ptext(p).startswith("Ⅰ."))
    colpr = COLPR_RE.search(ps[first_h1]).group()

    def clean(p):
        return COLPR_RE.sub("", p)

    h1 = clean(ps[first_h1])
    blank = SEG_RE.sub("", ps[first_h1 - 1])
    h2 = clean(next(p for p in ps[first_h1:] if ptext(p).startswith("1.1")))
    body = clean(next(p for p in ps[first_h1:] if ptext(p) == "{{본문 단락}}"))
    ref = next(p for p in ps[first_h1:] if ptext(p).startswith("{{참고문헌"))
    label_ref = ps[ps.index(ref) - 2]
    link_cid, header = _link_style(header, ref)

    # 앞부분 (저자 줄은 각주 포함해서 다시 만든다)
    out = []
    for p in ps[:first_h1]:
        if ptext(p).startswith("{{저자1}}"):
            cid = re.search(r'charPrIDRef="(\d+)"', p).group(1)
            tag = re.match(r"<hp:p [^>]*>", p).group()
            p = tag + authors_runs(names_of(spec["authors_ko"]), spec.get("notes", []), cid,
                                          bool(spec.get("note_marker"))) + "</hp:p>"
        out.append(fill_front(p, spec))
    out.append(blank)

    counter = {"id": 9000, "table": 0, "figure": 0}
    figs = []

    def uid():
        counter["id"] += 1
        return counter["id"]

    def emit(items):
        for it in items:
            if isinstance(it, str):
                out.append(with_text(body, it))
            elif "table" in it:
                counter["table"] += 1
                t = it["table"]
                out.extend([caption("table", counter["table"], t["caption"]),
                            table_para(t["rows"], uid, t.get("header", True)), blank])
            elif "figure" in it:
                counter["figure"] += 1
                f = it["figure"]
                token = "§FIG%02d§" % counter["figure"]
                figs.append((token, Path(f["path"]).resolve(), f.get("width_mm", FIG_MM)))
                out.extend([figure_para(token),
                            caption("figure", counter["figure"], f["caption"]), blank])
            else:
                raise ValueError("본문 항목은 문자열, {table}, {figure} 중 하나여야 합니다")

    for n, s in enumerate(spec["sections"]):
        if n > 0:
            out += [blank, blank]
        head = with_text(h1, "%s. %s" % (ROMAN[n], s["heading"]))
        if n == 0:   # 첫 장 제목에서 본문 2단 시작
            head = head.replace("<hp:t>", colpr + "<hp:t>", 1)
        out += [head, blank]
        emit(s.get("paragraphs", []))
        for m, sub in enumerate(s.get("subsections", []), 1):
            out += [with_text(h2, "%d.%d %s" % (n + 1, m, sub["heading"])), blank]
            emit(sub.get("paragraphs", []))

    out += [blank, blank, SEG_RE.sub("", label_ref), blank]
    uid_link = [5000]
    cid = re.search(r'charPrIDRef="(\d+)"', ref).group(1)
    for r in spec["references"]:
        out.append(with_runs(ref, _ref_runs(r, cid, link_cid, uid_link)))

    new_sec = pre + "".join(out) + post
    if spec.get("note_marker"):   # 각주 기호를 번호 대신 지정 문자(예: "*")로 (각주가 1개일 때)
        new_sec = new_sec.replace(
            'type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="1"',
            'type="USER_CHAR" userChar="%s" prefixChar="" suffixChar="" supscript="0"'
            % esc(spec["note_marker"]), 1)

    def patch(name, d):
        if name == "Contents/section0.xml":
            return new_sec.encode("utf8")
        if name == "Contents/header.xml":
            return header.encode("utf8")
        if name == "Preview/PrvText.txt":
            return spec["title_ko"].encode("utf8")
        return drop_bindata(name, d)

    out_path = Path(out_path)
    out_path.write_bytes(rewrite_zip(TEMPLATE.read_bytes(), patch))
    if figs:
        add_figures(out_path, figs)


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
            runs.append(run(text[pos:m.start()], cid))
        uid[0] += 2
        runs.append(fh._hyperlink_run_xml(link_cid, uid[0], uid[0] + 1, m.group(), m.group()))
        pos = m.end()
    if pos < len(text):
        runs.append(run(text[pos:], cid))
    return "".join(runs)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: make_paper.py paper.json output.hwpx")
    build(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), sys.argv[2])
    print("saved", sys.argv[2])
