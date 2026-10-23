# 🦊 리안뽁스 디스코드 게임 추천 & 스팀 실시간 세일 대시보드 (무료 클라우드 자동화 키트)

이 압축 파일에는 **컴퓨터를 꺼두어도 100% 무료로 작동하는** 디스코드 포럼 + 스팀 실시간 세일 웹 대시보드 파일이 모두 들어 있습니다.

---

## 📁 포함된 파일 목록
1. `index.html` : 시청자들과 링크로 공유할 수 있는 인터랙티브 웹 대시보드
2. `games.json` : 기존 노션에 정리해 두셨던 **37개 게임 데이터**가 초기값으로 들어 있는 데이터 파일
3. `sync_discord_and_steam.py` : 디스코드 포럼 채널(`1532791025729404998`)의 글, **14개 태그**, **👍 따봉 반응수**, 그리고 **스팀 한국 스토어(KRW) 실시간 세일 가격**을 자동으로 읽어와 `games.json`을 업데이트하는 파이썬 스크립트
4. `.github/workflows/sync.yml` : 내 컴퓨터가 꺼져 있어도 GitHub 클라우드가 2시간마다(또는 버튼 클릭 시마다) 자동으로 스크립트를 실행해 주는 설정 파일

---

## 🚀 5분 만에 무료 클라우드 연결하기 (따라하기 가이드)

### 1단계: 디스코드 봇 토큰 발급 및 서버 초대
1. [Discord Developer Portal](https://discord.com/developers/applications)에 접속해 우측 상단 **New Application**을 클릭하고 이름을 `리안뽁스 게임봇`으로 만듭니다.
2. 좌측 메뉴 **Bot**으로 이동해 **Reset Token**을 눌러 **Bot Token(비밀번호 같은 문자열)**을 복사해 메모장에 적어둡니다.
3. 같은 페이지 아래쪽 **Privileged Gateway Intents** 항목에서 **Message Content Intent**(메시지 본문 읽기 권한)를 **켬(ON)**으로 체크하고 저장(Save Changes)합니다.
4. 좌측 메뉴 **OAuth2** -> **URL Generator**로 이동합니다:
   - **SCOPES**에서 `bot` 체크
   - **BOT PERMISSIONS**에서 `View Channels`(채널 보기), `Read Message History`(메시지 기록 보기) 체크
5. 맨 아래 생성된 URL을 복사해 인터넷 주소창에 붙여넣고, **리안뽁스 디스코드 서버**에 봇을 초대합니다.

---

### 2단계: GitHub 무료 저장소 만들고 파일 올리기
1. [GitHub](https://github.com/)에 로그인한 뒤 우측 상단 `+` 버튼 -> **New repository**를 클릭합니다.
2. Repository 이름을 예를 들어 `rianfox-games`로 적고 **Public**을 선택한 뒤 **Create repository**를 누릅니다.
3. 생성된 저장소 화면에서 **uploading an existing file**을 눌러, 이 압축 파일 안의 4개 파일(`index.html`, `games.json`, `sync_discord_and_steam.py`, `.github/workflows/sync.yml`)을 그대로 드래그해서 올리고 **Commit changes**를 누릅니다.

---

### 3단계: 디스코드 봇 토큰 등록 & 웹사이트 켜기
1. GitHub 저장소 상단 메뉴 **Settings** -> 좌측 메뉴 **Secrets and variables** -> **Actions**로 이동합니다.
2. **New repository secret** 버튼을 누르고:
   - **Name**: `DISCORD_BOT_TOKEN`
   - **Secret**: 1단계에서 복사해 둔 디스코드 봇 토큰 붙여넣기
   - **Add secret** 클릭!
3. 같은 **Settings**에서 좌측 메뉴 **Pages**로 이동한 뒤, **Branch**를 `main`으로 선택하고 **Save**를 누릅니다.
4. 약 1분 뒤 `https://[본인깃허브아이디].github.io/rianfox-games/` 주소로 나만의 인터랙티브 웹 대시보드가 열립니다!

---

## 💡 평소에는 어떻게 쓰나요?
- **시청자**: 기존 가이드라인 그대로 디스코드 포럼에 추천 글을 올리고 👍 이모지를 누릅니다.
- **리안뽁스님**: 디스코드 포럼에서 글에 **`🦊 리안뽁스 취향!`**, **`👀 찜 목록 추가 완료`**, **`🎮 플레이 예정/플레이 중`**, **`✅ 플레이 완료`** 태그만 붙여주시면 됩니다!
- **자동 업데이트**: 컴퓨터를 꺼두어도 2시간마다(또는 GitHub의 **Actions** 탭에서 **Run workflow** 버튼을 누르면 10초 만에 즉시) 웹사이트에 새 게임, 👍 추천수, 그리고 **오늘 스팀에서 할인 중인지 여부**가 자동으로 반영됩니다.
