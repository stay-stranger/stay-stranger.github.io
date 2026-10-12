#!/usr/bin/env python3
"""advisor/_src/*.md → advisor/*.html 변환기 (어드바이저 시리즈 전용).

사용: python3 _tools/md2post.py
글투는 ~/.claude/skills/narrative-tech-prose, 구조는 CLAUDE.md 를 따른다.

블로그 CLAUDE.md 의 컴포넌트 어휘(.code/.note/.table-wrap/.closing …)로만 렌더링하고,
공개 전 익명화 치환을 변환 단계에서 강제한다.
"""
import html
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "advisor" / "_src"
OUT = SRC.parent

# ---------------------------------------------------------------- 익명화 (순서 중요)
REPLACEMENTS = [
    ("docker exec -it korean-rag-mariadb mariadb -uroot -proot123 wecoms_dev",
     "docker exec -it mariadb mariadb -u <계정> -p local_db"),
    ("# 로그인 호출 (계정: admin / admin123!)", "# 로그인 호출 (로컬 테스트 계정)"),
    ("# ⚠️ 비밀번호에 ! 가 있어 bash 이스케이프 문제 발생 → 파일로 만들어 전송",
     "# 본문(JSON)은 파일로 만들어 전송한다"),
    ("username='admin'", "username='<username>'"),
    ("Flow Advisor", "어드바이저"),
    ("Flow Agent", "데스크톱 에이전트"),
    ("wecoms_dev", "local_db"),
    ("(ACS/아이프론)", "(교환기 연동 시스템)"),
    ("(아이프론이 빈 발화를 보낸다)", "(연동 시스템이 빈 발화를 보낸다)"),
    ("아이프론", "교환기 연동 시스템"),
    ("X-Ipron-Tenant-Id", "X-Tenant-Id"),
    ("인터넷 노출 운영이 local 프로파일로 구동된 이력", "운영 환경이 local 프로파일로 구동된 이력"),
]
FORBIDDEN = re.compile(r"wecoms|WECOMS|admin123|root123|test123|ipron|Ipron|아이프론|보험개발원|삼성카드|예다함|/Users/", re.I)

EMOJI_STRIP = re.compile(r"[⭐⚠️🔴✅📌🔑💡❓🎯📍🧠🔄📊🔍]+\s?")

# ---------------------------------------------------------------- 인라인
def inline(text: str) -> str:
    codes = []
    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes)-1}\x00"
    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    text = text.replace("❌", "✗").replace("✅", "✓")
    text = EMOJI_STRIP.sub("", text)
    def unstash(m):
        return f"<code>{html.escape(codes[int(m.group(1))], quote=False)}</code>"
    return re.sub(r"\x00(\d+)\x00", unstash, text)

# ---------------------------------------------------------------- 블록 파서
def parse(md: str):
    lines = md.splitlines()
    blocks, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1; continue
        if line.startswith("```"):
            lang = line[3:].strip(); body = []; i += 1
            while i < n and not lines[i].startswith("```"):
                body.append(lines[i]); i += 1
            i += 1
            blocks.append(("code", lang, "\n".join(body))); continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2).strip())); i += 1; continue
        if re.match(r"^-{3,}$", line.strip()):
            i += 1; continue
        if line.startswith(">"):
            q = []
            while i < n and lines[i].startswith(">"):
                q.append(lines[i][1:].lstrip()); i += 1
            blocks.append(("quote", q)); continue
        if line.startswith("|"):
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append(lines[i]); i += 1
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            cells = [c for c in cells if not all(re.match(r"^:?-{2,}:?$", x) for x in c)]
            blocks.append(("table", cells[0], cells[1:])); continue
        if re.match(r"^(\s*)([-*]|\d+[.)])\s+", line):
            items = []
            while i < n and (re.match(r"^(\s*)([-*]|\d+[.)])\s+", lines[i]) or (lines[i].startswith("   ") and items)):
                mm = re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", lines[i])
                if mm:
                    indent = len(mm.group(1)); ordered = mm.group(2)[0].isdigit()
                    txt = re.sub(r"^\[[ x]\]\s*", "", mm.group(3))
                    items.append([indent, ordered, txt])
                else:
                    items[-1][2] += " " + lines[i].strip()
                i += 1
            blocks.append(("list", items)); continue
        para = []
        while i < n and lines[i].strip() and not re.match(r"^(#{1,4}\s|```|>|\||-{3,}$|\s*([-*]|\d+[.)])\s+)", lines[i]):
            para.append(lines[i].strip()); i += 1
        blocks.append(("p", " ".join(para)))
    return blocks

# ---------------------------------------------------------------- 렌더러
LANG_HEAD = {"sql": "SQL", "bash": "BASH", "java": "JAVA", "typescript": "TYPESCRIPT", "": "도식"}

def render_code(lang, body):
    head = LANG_HEAD.get(lang, lang.upper())
    rows = body.split("\n")
    if rows and re.match(r"^\s*(//|#|--)\s*\S+\.(java|tsx?|ya?ml|json)(:\d+)?\s*$", rows[0]):
        head = re.sub(r"^\s*(//|#|--)\s*", "", rows[0]); rows = rows[1:]
    out = []
    for r in rows:
        e = html.escape(r, quote=False).replace("❌", "✗").replace("✅", "✓")
        s = r.strip()
        if "✗" in e or "❌" in r:
            e = f'<span class="c-bad">{e}</span>'
        elif s.startswith(("# ", "-- ", "// ")) or s in ("#", "--", "//"):
            e = f'<span class="c-dim">{e}</span>'
        elif "★" in r or "←" in r and lang in ("java", "typescript"):
            e = f'<span class="c-acc">{e}</span>'
        out.append(e)
    return (f'      <div class="code">\n        <div class="code-head">{html.escape(head)}</div>\n'
            f'<pre>{chr(10).join(out)}</pre>\n      </div>\n')

def render_table(head, rows):
    def td(c, first):
        t = inline(c)
        cls = []
        if first and re.fullmatch(r"<code>.*</code>", t): cls.append("scope-name")
        if len(c) > 26: cls.append("wrap")
        return f'<td{" class=%s" % chr(34)+" ".join(cls)+chr(34) if cls else ""}>{t}</td>'
    ths = "".join(f"<th>{inline(h)}</th>" for h in head)
    body = "\n".join("            <tr>" + "".join(td(c, j == 0) for j, c in enumerate(r)) + "</tr>" for r in rows)
    return ('      <div class="table-wrap">\n        <table>\n'
            f'          <thead><tr>{ths}</tr></thead>\n          <tbody>\n{body}\n          </tbody>\n'
            '        </table>\n      </div>\n')

def render_quote(q):
    text = " ".join(q).strip()
    kind = ""
    if re.match(r"^(🔴|⚠️)", text): kind = " is-warn"
    elif re.match(r"^(🔑|💡)", text): kind = " is-key"
    text = EMOJI_STRIP.sub("", text).strip()
    title = {" is-warn": "함정", " is-key": "기억할 규칙"}.get(kind, "")
    m = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", text, re.S)
    if m and len(m.group(1)) < 60:
        title, text = m.group(1), m.group(2)
    paras = [p for p in re.split(r"\s{2,}|(?<=\.)\s(?=[A-Z가-힣])", text) if p] if False else [text]
    inner = "".join(f"        <p>{inline(p)}</p>\n" for p in paras)
    t = f'        <p class="note-title">{inline(title)}</p>\n' if title else ""
    return f'      <div class="note{kind}">\n{t}{inner}      </div>\n'

def render_list(items):
    # 2단계 들여쓰기 지원
    out = []; stack = []
    for indent, ordered, txt in items:
        tag = "ol" if ordered else "ul"
        while stack and stack[-1][0] > indent:
            out.append(f"</{stack.pop()[1]}></li>")
        if not stack or stack[-1][0] < indent:
            if stack: out[-1] = out[-1][:-5]  # 직전 </li> 제거해 중첩
            out.append(f"<{tag}>"); stack.append((indent, tag))
        out.append(f"<li>{inline(txt)}</li>")
    while stack:
        out.append(f"</{stack.pop()[1]}>")
    s = "".join(out)
    s = s.replace("</li><ul>", "<ul>").replace("</li><ol>", "<ol>")
    return "      " + s + "\n"

def strip_heading(t):
    return EMOJI_STRIP.sub("", t).strip()

def build(cfg):
    md = (SRC / cfg["src"]).read_text(encoding="utf-8")
    for a, b in REPLACEMENTS:
        md = md.replace(a, b)
    blocks = parse(md)

    # h2 단위로 섹션 분할 (첫 h1 과 첫 인용(메타)은 버림)
    sections, cur, preface = [], None, []
    for b in blocks:
        if b[0] == "h" and b[1] == 1: continue
        if b[0] == "h" and b[1] == 2:
            cur = {"title": strip_heading(b[2]), "body": []}; sections.append(cur); continue
        if cur is None:
            if b[0] == "quote" and any("갱신 요지" in q for q in b[1]):
                preface.append(render_quote(b[1]))
            continue  # 머리말 메타 인용은 meta-strip 으로 대체
        cur["body"].append(b)
    sections = [s for s in sections if not any(d in s["title"] for d in cfg.get("drop", []))]

    # 절 번호는 원문 번호를 유지한다 (본문이 "→ 3.2", "7절" 처럼 참조하기 때문). 부록은 마지막+1.
    nums = []
    for s in sections:
        m = re.match(r"^(\d+)\.", s["title"])
        nums.append(int(m.group(1)) if m else (nums[-1] + 1 if nums else 1))
    from_zero = nums and nums[0] == 0
    toc, main = [], []
    for idx, s in enumerate(sections, 1):
        num = nums[idx - 1]
        title = re.sub(r"^\d+\.\s*", "", s["title"])
        title = re.sub(r"^부록:\s*", "", title)
        sid = f"s{num}"
        toc.append(f'      <li><a href="#{sid}">{inline(title)}</a></li>')
        lede = cfg["ledes"][idx - 1]
        out = [f'    <section id="{sid}">\n      <h2><span class="num">{num:02d}</span><span>{inline(title)}</span></h2>\n'
               f'      <p class="lede">{inline(lede)}</p>\n']
        body = s["body"]
        for j, b in enumerate(body):
            k = b[0]
            if k == "h":
                out.append(f"      <h3>{inline(strip_heading(b[2]))}</h3>\n")
            elif k == "p":
                t = b[1]
                if t.endswith("*") and t.startswith("*") and "문서 끝" in t: continue
                mm = re.fullmatch(r"\*\*(.+?)\*\*", t)
                if mm and len(t) < 40:
                    out.append(f"      <h3>{inline(mm.group(1))}</h3>\n")
                else:
                    out.append(f"      <p>{inline(t)}</p>\n")
            elif k == "code": out.append(render_code(b[1], b[2]))
            elif k == "table": out.append(render_table(b[1], b[2]))
            elif k == "quote": out.append(render_quote(b[1]))
            elif k == "list": out.append(render_list(b[1]))
        out.append("    </section>\n")
        main.append("".join(out))

    meta = "".join(f"      <span><b>{html.escape(k)}</b> {html.escape(v)}</span>\n" for k, v in cfg["meta"])
    closing = "".join(f"        <li><strong>{html.escape(a)}</strong> {html.escape(b)}</li>\n" for a, b in cfg["closing"])
    nav = cfg["nav"]
    doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{html.escape(cfg['description'])}">
<title>{html.escape(cfg['title'])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+KR:wght@300;400;500;600;700&display=swap">
<link rel="stylesheet" href="/assets/css/post.css">
</head>
<body>
<nav class="sitenav"><a href="/">← stay-stranger</a> <span class="sitenav-sep">/</span> <a href="/advisor/">어드바이저</a></nav>

<div class="shell">

  <nav class="toc" aria-label="목차">
    <p class="toc-label">목차</p>
    <ol{' class="from-zero"' if from_zero else ''}>
{chr(10).join(toc)}
    </ol>
  </nav>

  <main class="doc">

    <p class="eyebrow">{html.escape(cfg['eyebrow'])}</p>
    <h1>{html.escape(cfg['title'])}</h1>
    <p class="standfirst">
      {cfg['standfirst']}
    </p>

    <div class="meta-strip">
{meta}    </div>

{"".join(preface)}
{"".join(main)}
    <hr class="rule">

    <div class="closing">
      <h2><span class="num">■</span><span>기억할 것</span></h2>
      <ol>
{closing}      </ol>
    </div>

    <div class="note">
      <p class="note-title">시리즈</p>
      <p>{nav}</p>
    </div>

  </main>
</div>

</body>
</html>
"""
    bad = FORBIDDEN.findall(doc)
    if bad:
        sys.exit(f"[{cfg['out']}] 익명화 실패: {sorted(set(bad))}")
    (OUT / cfg["out"]).write_text(doc, encoding="utf-8")
    print(f"wrote {OUT / cfg['out']}  sections={len(sections)}  bytes={len(doc.encode())}")

# ---------------------------------------------------------------- 문서별 설정
DOCS = [
    dict(
        src="01_study_guide.md", out="study-guide.html",
        title="어드바이저 코드베이스 학습 가이드",
        eyebrow="코드베이스 학습 · 길잡이",
        description="Java 파일 7,814개, 모듈 61개짜리 저장소를 처음 받아 든 사람을 위한 읽기 순서. 전체의 9%에서 시작해 자주 다니는 길부터 발에 익힌다.",
        standfirst="저장소를 받아 파일 수를 세어 본 날, 전부 이해하겠다는 계획을 접었다. Java 파일 7,814개와 모듈 61개 앞에서 지도를 외우는 사람은 없다. 대신 자주 다니는 길 몇 개를 먼저 발에 익히고 나머지는 지도를 꺼내 보기로 했다. 이 글은 그 길의 순서다. 전체의 <strong>9%</strong>에서 시작한다.",
        meta=[("작성", "2026-07-27"), ("재측정", "2026-10-12 · 커밋 f06317ca47"), ("규모", "Java 7,814 · 모듈 61 · 마이그레이션 1,127")],
        drop=["폐쇄망"],
        ledes=[
            "숫자를 먼저 보고, 목표를 바꾼다.",
            "어디서 시작해 어디로 가는지. 일곱 단계와 그 순서의 이유.",
            "어떤 모듈이든 같은 다섯 단계로 연다. 이 가이드의 핵심 도구다.",
            "137개 파일 중 여섯. 명부를 적는 필터와 문을 지키는 매트릭스.",
            "로그인 그 순간의 일. core/security 와 무엇이 다른지.",
            "코드보다 DB 를 먼저 본다. 엔티티 아홉과 시드 함정, 그리고 7월 이후 가장 많이 바뀐 자리.",
            "가장 작은 모듈로 손을 만든다. 글 하나로 따로 뗐다.",
            "제품의 심장. 테이블 다섯의 관계와 상태 전이, 그리고 Cron 을 보는 스케줄러는 하나뿐이라는 것.",
            "3~6단계는 지도만 그려 둔다. 길은 필요해질 때 걷는다.",
            "매일 치는 명령과 포트.",
            "모르고 밟으면 장애가 되는 규칙. 초반에 자주 밟는 것만.",
            "여덟 문항에 답할 수 있으면 0~2단계가 끝난 것이다.",
        ],
        closing=[
            ("전부 이해하는 건 목표가 아니다.", "필요한 자리에 빠르게 도달하는 능력이 목표다. 0~2단계가 전체 Java 파일의 9% 남짓이다."),
            ("모듈은 전부 같은 손으로 열린다.", "entity 로 명사를, DB 로 실데이터를, controller 로 동사를 보고 service 메서드 하나를 끝까지 따라간다."),
            ("DB SELECT 를 건너뛰지 않는다.", "실제 행 열 개를 본 뒤에 엔티티를 다시 열면 컬럼 이름이 아는 얼굴이 된다."),
            ("6단계는 필요해지기 전에 손대지 않는다.", "가장 어렵고 가장 자주 바뀐다."),
        ],
        nav='<a href="/advisor/">목차</a> · 다음: <a href="/advisor/auth-permission-menu.html">인증 · 권한 · 메뉴 체계</a>',
    ),
    dict(
        src="02_auth_permission_menu.md", out="auth-permission-menu.html",
        title="인증 · 권한 · 메뉴 체계",
        eyebrow="Spring Security · 구조 해설 · 0단계",
        description="요청 하나가 지나는 문 셋. 필터는 이름을 적고, URL 매트릭스가 막고, '자기 것만'은 서비스 코드가 맡는다. 401·403·안 보이는 메뉴가 그 셋으로 설명된다.",
        standfirst="처음 이 저장소의 보안 설정을 열었을 때 나는 요청을 막는 코드를 찾고 있었다. 필터에는 그런 코드가 없었다. 필터는 이름을 적을 뿐이고, 막는 건 뒤에 선 문이고, <strong>'자기 것만'</strong>은 어떤 애너테이션도 말할 줄 몰라 서비스 코드가 맡는다. 이 셋을 따로 놓고 보면 401 과 403 과 안 보이는 메뉴가 전부 한 그림 안에 들어온다.",
        meta=[("작성", "2026-07-27"), ("재측정", "2026-10-12 · 커밋 f06317ca47"), ("범위", "core/security · core/config · permission · web-react 메뉴")],
        ledes=[
            "문이 셋이다. 셋이 묻는 질문이 전부 다르다.",
            "이름을 적되 막지는 않는 필터. 401 과 403 이 갈리는 자리.",
            "파일이 셋이고 줄의 순서가 로직이다. 매트릭스를 읽는 다섯 가지 개념.",
            "토큰이 아직 없는 첫 요청이 설정 안에서 지나가는 길.",
            "7월에 467건이던 hasRole 이 1건이 됐다. 그 사이에 무엇이 저장소를 지나갔나.",
            "users 에서 menus 까지 이어지는 사슬. 메뉴 권한과 기능 권한은 같은 서랍에 있다.",
            "메뉴의 원본은 BE JSON 이 됐고, 두 곳을 잇는 열쇠는 path 다.",
            "3줄 규칙과 /my 패턴, 그리고 역할로는 표현할 수 없는 삭제 권한.",
            "에러 없이 실패하는 자리 아홉.",
            "열 문항.",
            "관심사별로 열어야 할 파일.",
        ],
        closing=[
            ("필터는 적고, 매트릭스가 막는다.", "401 이면 토큰 문제, 403 이면 권한 문제다."),
            ("API 인가는 인증 여부로만 한다.", "hasRole 은 한 건 남았다. 되돌리기 어려운 행위는 hasFeature, 범위는 서비스, 메뉴 노출은 매트릭스."),
            ("@PreAuthorize 는 범위를 말할 줄 모른다.", "'자기 것만'은 서비스 코드가 토큰에서 신원을 꺼내 덮어쓴다."),
            ("path 가 접착제다.", "menu-definition.json 과 menu.ts 의 path 가 어긋나면 에러 없이 메뉴가 사라진다."),
            ("단건은 403 이 아니라 404 다.", "존재 여부를 흘리지 않는다."),
        ],
        nav='<a href="/advisor/">목차</a> · 이전: <a href="/advisor/study-guide.html">학습 가이드</a> · 다음: <a href="/advisor/stt-module.html">stt 모듈</a>',
    ),
    dict(
        src="03_stt_module.md", out="stt-module.html",
        title="stt 모듈 — 모듈 구조 패턴 체득",
        eyebrow="모듈 읽기 · 1단계",
        description="가장 작은 업무 모듈 하나로 모듈 읽는 손을 만든다. 통화 이벤트와 발화가 처음 닿는 강어귀. 파일 여섯, 메서드 둘.",
        standfirst="stt 는 강어귀다. 바깥에서 흘러온 통화 이벤트와 발화가 처음 닿는 자리이고, 여기서 하는 일은 받아 두고 어디로 흘려보낼지 정하는 것뿐이다. 분석도 평가도 하지 않는다. 그래서 가장 작고, 그래서 모듈 하나를 읽는 손을 만들기에 가장 좋다. 파일 여섯과 메서드 둘을 끝까지 따라가면 나머지 <strong>60개 모듈</strong>에서 어디를 봐야 할지 몸이 먼저 안다.",
        meta=[("작성", "2026-10-12"), ("기준 커밋", "f06317ca47"), ("실측", "로컬 DB · 통화 107건 · 발화 2,774건")],
        ledes=[
            "STT 가 아니라 손을 익히는 단계. 7월 뒤에 바뀐 것부터.",
            "강어귀. 받고, 저장하고, 흘려보내고, 끝났다고 알린다.",
            "파일 여섯과 각 파일에서 볼 줄 범위.",
            "명사 둘. 화자를 적는 칸에 세 가지 뜻이 겹쳐 쌓인 사연.",
            "코드 전에 데이터. 쿼리 넷.",
            "밖에서 할 수 있는 동사. 수신 메서드 하나를 일곱 단계로 따라간다.",
            "저장 메서드 하나와, 거기서 애너테이션 한 줄이 떨어져 나간 날.",
            "AI 소프트폰 통화에서 두 벌 들어오는 STT 중 무엇을 버리는가.",
            "이벤트 둘이 다음 모듈로 건너가는 다리다.",
            "AI 호출이 붙으면 모듈이 어떻게 달라지나.",
            "아홉 가지.",
            "열 문항. 여덟 이상이면 2단계로.",
            "관심사별 파일 위치.",
        ],
        closing=[
            ("stt 는 강어귀다.", "받아 두고 흘려보낼 뿐, 분석·평가·요약은 다른 모듈이 이벤트를 받아서 한다."),
            ("화자는 call_type 이고, 유틸을 거쳐서만 판정한다.", "channel_type 은 세 가지 뜻이 겹쳐 쌓인 폐기 컬럼이다."),
            ("저장이 먼저, 전송은 그다음.", "화면에는 떴는데 DB 에는 없는 발화를 만들지 않는다."),
            ("출구는 Spring 이벤트 둘.", "평가는 이 이벤트로 시작하지 않고 스케줄러가 긁어 간다."),
            ("수신 경로는 LLM 을 기다리지 않는다.", "2026-09-23 에 떨어져 나간 동기 교정 호출이 그 사례다."),
        ],
        nav='<a href="/advisor/">목차</a> · 이전: <a href="/advisor/auth-permission-menu.html">인증 · 권한 · 메뉴 체계</a> · 다음: <a href="/advisor/evaluation-module.html">evaluation 모듈</a>',
    ),
    dict(
        src="04_evaluation.md", out="evaluation-module.html",
        title="evaluation 모듈 — 핵심 업무 도메인",
        eyebrow="모듈 읽기 · 2단계",
        description="통화 한 건이 점수가 되기까지. 60초 폴링이 깨어나는 조건, DATA_READY 라는 자격, 트랜잭션 밖에서 도는 AI 호출, 그리고 cron 이 시계가 아닌 이유.",
        standfirst="평가는 이 제품이 파는 것이다. 통화 한 건이 점수 한 줄이 되기까지 테이블 넷과 파일 일곱을 지나고, 현업 문의의 대부분이 그 길 어딘가에서 생긴다. 스케줄러가 깨어나는 조건에서 시작해 AI 가 문항 하나에 점수를 매기는 자리까지 메서드 하나를 끝까지 따라간다. 먼저 알아 둘 것은 하나다. <strong>cron 은 시계가 아니다.</strong>",
        meta=[("작성", "2026-10-12"), ("기준 커밋", "f06317ca47"), ("실측", "로컬 DB · 계획 9 · 대상 20 · 결과 620(실제 20)")],
        ledes=[
            "스케줄 설정 테이블의 과거 날짜 일곱 줄에서 시작한다.",
            "모으고, 고르고, 묶고, 매기고, 알린다. 테이블 넷의 순서가 그 순서다.",
            "파일 일곱. stt 보다 하나 늘었고 그 하나가 가장 최근에 피를 본 자리다.",
            "명사 다섯과 자식 셋. 대상의 상태가 곧 평가받을 자격이다.",
            "쿼리 넷. 첫 번째가 이 글의 첫 문단이다.",
            "시계가 여섯인데 cron 을 보는 건 하나고, 그 하나도 cron 을 직접 보지 않는다.",
            "다리 둘을 건너 메서드 하나를 다섯 단계로. 긴 트랜잭션이 없는 이유.",
            "유형 셋, 호출 횟수, 합산 식. 성적표 한 장이 그 식 그대로다.",
            "들어오는 길 셋과 나가는 길 넷. 3단계와 6단계로 가는 다리.",
            "아홉 가지.",
            "열 문항. 여덟 이상이면 3단계로.",
            "관심사별 파일 위치.",
        ],
        closing=[
            ("cron 은 시계가 아니다.", "실행 판정은 next_execution_at 이 현재를 지났는가다. cron 은 다음 값을 계산할 때만 쓰인다."),
            ("DATA_READY 만 평가받는다.", "PENDING 은 발화가 없는 것, IN_PROGRESS 는 누가 집어 간 것이다."),
            ("SCHEDULE 은 대상 선택 방식이다.", "실행 방식은 execution_mode 다. 화면 표기는 '연동 대상 기준'."),
            ("배치 시작은 커밋 뒤, 한 곳에서.", "2026-09-24 운영 사고가 EvaluationBatchStarter 를 만들었다."),
            ("AI 호출 구간에는 트랜잭션이 없다.", "준비 · 루프 · 저장의 세 조각이고 DB 를 만지는 둘만 30초짜리 짧은 트랜잭션이다."),
        ],
        nav='<a href="/advisor/">목차</a> · 이전: <a href="/advisor/stt-module.html">stt 모듈</a> · 다음: 3단계 recording → sttanalytics (예정)',
    ),
]

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for cfg in DOCS:
        build(cfg)
