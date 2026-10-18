# 마토메 보드

일본 게임·애니·버튜버·만화 공연과 이벤트 소식을 모아 보는 공개 페이지입니다.
GitHub Pages로 공개되고, GitHub Actions가 하루 4번(일본 시간 6·12·18·24시) 소식을 자동으로 갱신합니다.

## 처음 한 번만 하는 설정

1. **저장소 만들기**: GitHub에서 새 저장소를 **Public**으로 만들고, 이 폴더의 파일을 전부 올립니다.
   (웹에서는 *Add file → Upload files*에 폴더째 끌어다 놓으면 됩니다. `.github` 폴더도 꼭 함께 올려 주세요.)
2. **페이지 공개**: *Settings → Pages*에서 *Source*를 `Deploy from a branch`, 브랜치 `main`, 폴더 `/ (root)`로 저장합니다.
   1~2분 뒤 `https://<아이디>.github.io/<저장소이름>/` 주소가 생깁니다. 이 주소를 친구에게 보내면 됩니다.
3. **자동 업데이트 권한**: *Settings → Actions → General → Workflow permissions*에서 `Read and write permissions`를 고릅니다.
4. **(선택) 키 등록**: *Settings → Secrets and variables → Actions → New repository secret*
   - `ANNICT_TOKEN`: annict.com 설정 → 애플리케이션에서 발급. 방영 목록 갱신과 공식 사이트 썸네일에 사용.
   - `HOLODEX_API_KEY`: holodex.net 계정 설정에서 발급. 버튜버 방송 예정에 사용. (키가 없어도 ホロライブ·にじさんじ·ぶいすぽっ 공식 뉴스와 PANORA 의 버튜버 이벤트·굿즈 소식은 들어옵니다.)
   키가 없어도 뉴스 수집과 PV 썸네일은 동작합니다.
5. **첫 실행**: *Actions → 소식 자동 업데이트 → Run workflow*. 이후로는 알아서 돌아갑니다.

## 운영하는 법

| 하고 싶은 것 | 고칠 파일 |
|---|---|
| 소식을 직접 추가 | `data/manual.json` |
| 공개 보드에서 소식 빼기 | `data/blocklist.json` (`urls`, `titles`에 추가) |
| 수집할 사이트 바꾸기 | `collector.py`의 `SOURCES` (고친 뒤 *Actions → 소스 점검 → Run workflow*로 OK/FAIL 확인) |
| 방송 요일·시각 고치기 | `data/anime.json` |

GitHub 웹에서 파일을 열고 연필 아이콘으로 고친 뒤 *Commit changes*를 누르면 몇 분 안에 반영됩니다.

`data/manual.json`에 넣는 소식 형식:

```json
[
  {
    "title": "행사 이름",
    "category": "live",
    "source": "출처",
    "works": ["작품명"],
    "eventDate": "2026-12-19T18:00",
    "endDate": "",
    "ticketOpen": "",
    "deadline": "",
    "venue": "장소",
    "ticketUrl": "https://eplus.jp/...",
    "url": "https://공식 공지 주소",
    "summary": "한 줄 요약"
  }
]
```

`category`는 `live`(공연) · `event`(이벤트) · `official`(공식 행사) · `doujin`(동인·온리전) · `collab`(콜라보) · `popup`(팝업) · `exhibit`(전시·원화전) · `manga`(만화 소식) · `goods` · `stream` · `campaign` · `other` 중 하나입니다. 날짜는 일본 시간입니다.

## 보는 사람 입장

- 로그인이나 설정 없이 누구나 봅니다. 피드에서 버튜버만 고르거나 날짜순으로 볼 수 있고, 캘린더에서 날을 누르면 그날 일정이 나옵니다.
- "방영중"의 ‘보는 중’ 목록만 각자 브라우저에 저장되고, 그 밖의 개인 설정은 없습니다. 특정 소식을 빼고 싶으면 운영자가 `data/blocklist.json`에 넣습니다.
- 소식은 공식 사이트와 뉴스 RSS에서 자동으로 모으므로 날짜·예약 정보는 원문에서 꼭 확인하도록 안내돼 있습니다.

## 게시판 설정 (한 번만)

"사이트 개요" 탭의 게시판은 누구나 익명으로 쓰고, 올린 글은 고치거나 지울 수 없습니다. 정적 페이지라 글을 담아 둘 곳이 필요한데, Google 폼(쓰기)과 응답 시트(읽기)를 씁니다. 설정 전에는 "준비 중"으로 보입니다.

1. **Google 폼 만들기**: 질문 두 개를 만듭니다. `이름`(단답형, 선택) · `내용`(장문형, 필수). 설정 탭에서 *이메일 주소 수집*을 끄고, *응답 1회로 제한*을 끕니다(로그인 없이 쓰게 하려면 꼭).
2. **응답 시트 연결**: 폼의 *응답* 탭 → 스프레드시트 아이콘 → 새 스프레드시트 만들기.
3. **필드 이름 알아내기**: 폼 오른쪽 위 ⋮ → *미리 채워진 링크 가져오기* → 두 질문에 아무 값이나 넣고 *링크 보기* → 링크에 보이는 `entry.숫자`가 각 질문의 필드 이름입니다. 폼 주소 `https://docs.google.com/forms/d/e/폼ID/viewform`에서 `viewform`을 `formResponse`로 바꾼 것이 제출 주소입니다.
4. **시트 공개**: 스프레드시트에서 *파일 → 공유 → 웹에 게시* → 응답 시트 선택, 형식 *쉼표로 구분된 값(.csv)* → 게시 → 링크 복사.
5. **index.html 채우기**: 파일 위쪽의 `BBS` 네 값(`form`, `nameField`, `textField`, `csv`)에 넣고 커밋합니다.

글을 지워야 하면 응답 스프레드시트에서 해당 행을 삭제하면 됩니다. 같은 브라우저에서는 30초에 한 번만 올릴 수 있고, 글은 500자까지입니다.

## 참고

- 썸네일은 작품 공식 사이트의 대표 이미지(og:image)를 작게 줄여 `data/thumbs/`에 저장해 씁니다. 공식 사이트가 없으면 공식 PV 대표 이미지를 씁니다.
- 기사 본문은 저장하지 않고 제목·요약·원문 링크만 담습니다.
