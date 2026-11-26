# conference-paper-skill

학술대회 논문 양식(HWPX)으로 논문을 작성하는 Claude Code 스킬입니다. 특정 학회·개인 정보는 포함하지 않은 범용 양식입니다.

## 규칙 요약
- 국문/영문 제목·저자 → 요약 → 키워드 → 본문(Ⅰ, Ⅱ… / 1.1…) → 참고문헌 구조 유지
- 출처 URL은 **클릭 가능한 하이퍼링크**로 자동 변환
- 머리말(학회명, 좌측) + 바닥글 **쪽번호**(가운데)
- 저자 소속·직위·이메일은 **첫 쪽 하단 각주**(구분선 포함)
- 본문 중간에 **표·그림**(번호 캡션 자동) 삽입
- 원본 템플릿은 수정하지 않고 새 파일로 저장

## 설치
1. 의존 스킬 [hwpx-skill](https://github.com/jkf87/hwpx-skill)을 `~/.claude/skills/hwpx`에 설치하고 `pip install lxml jsonschema Pillow`
2. 이 저장소의 스킬 폴더를 복사
   ```bash
   cp -r skills/conference-paper-hwpx ~/.claude/skills/
   ```
3. Claude Code에서 "학술대회 논문 양식으로 ○○ 주제 논문 써줘"라고 요청

## 구성
```
skills/conference-paper-hwpx/
├── SKILL.md              # 작성·디자인 규칙과 절차
├── assets/template.hwpx  # 자리표시자가 들어 있는 양식
├── scripts/make_paper.py # JSON → HWPX 생성기
├── examples/sample.json  # 입력 예시 (표·그림 포함)
└── examples/sample_figure.png
```

## 예시 결과물
`skills/conference-paper-hwpx/examples/sample_output.hwpx` — `sample.json` 으로 생성한 예시(한컴오피스에서 열기).

직접 만들어 보려면:
```bash
cd skills/conference-paper-hwpx/examples
python ../scripts/make_paper.py sample.json my_paper.hwpx
```
