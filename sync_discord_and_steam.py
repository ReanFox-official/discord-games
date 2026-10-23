#!/usr/bin/env python3
"""
리안뽁스 디스코드 게임 추천 포럼 + 스팀 실시간 세일 가격 자동 동기화 스크립트
- 컴퓨터를 꺼두어도 GitHub Actions에서 주기적으로 실행되어 games.json을 업데이트합니다.
- 디스코드 서버 ID: 1519607626869117089 / 포럼 채널 ID: 1532791025729404998
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "1519607626869117089").strip()
FORUM_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "1532791025729404998").strip()

DISCORD_API_BASE = "https://discord.com/api/v10"

# 사진으로 보내주신 14개 디스코드 포럼 태그 분류
GENRE_TAG_NAMES = {"메트로베니아", "어드벤처", "퍼즐", "추리", "액션", "힐링", "공포"}
DIFFICULTY_TAG_NAMES = {"쉬움", "보통", "어려움"}
STATUS_TAG_NAMES = {
    "👀 찜 목록 추가 완료",
    "찜 목록 추가 완료",
    "🎮 플레이 예정/플레이 중",
    "플레이 예정/플레이 중",
    "✅ 플레이 완료",
    "플레이 완료",
}


def discord_get(path: str):
    """Discord REST API GET 호출"""
    url = f"{DISCORD_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "User-Agent": "RianfoxGameSyncBot/1.0",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_steam_price_krw(steam_url: str) -> dict:
    """
    스팀 상점 URL에서 App ID를 추출한 뒤,
    Steam 공식 Store API(cc=kr, l=korean)를 호출해 현재 원화 정가/할인가/세일 여부를 반환합니다.
    """
    if not steam_url:
        return {}
    match = re.search(r"store\.steampowered\.com/app/(\d+)", steam_url)
    if not match:
        return {}

    app_id = match.group(1)
    api_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=kr&l=korean"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Mozilla/5.0 (RianfoxGameDashboard/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        app_info = data.get(str(app_id), {})
        if not app_info.get("success"):
            return {}

        info = app_info.get("data", {})
        is_free = info.get("is_free", False)
        price_overview = info.get("price_overview", {})
        header_image = info.get("header_image", "")

        if is_free:
            return {
                "appId": app_id,
                "regularPrice": 0,
                "currentPrice": 0,
                "discountPercent": 0,
                "isOnSale": False,
                "headerImage": header_image,
            }

        if price_overview:
            # Steam KRW price_overview values are in 1/100 units (cents)
            initial_krw = int(price_overview.get("initial", 0) // 100)
            final_krw = int(price_overview.get("final", 0) // 100)
            discount_pct = int(price_overview.get("discount_percent", 0))
            return {
                "appId": app_id,
                "regularPrice": initial_krw,
                "currentPrice": final_krw,
                "discountPercent": discount_pct,
                "isOnSale": discount_pct > 0,
                "headerImage": header_image,
            }
    except Exception as exc:
        print(f"[WARN] Steam API 조회 실패 ({steam_url}): {exc}")

    return {}


def parse_guideline_message(content: str, thread_title: str) -> dict:
    """
    리안뽁스 게임 추천 채널 가이드라인 텍스트 파싱:
    게임 이름 :
    장르 :
    플랫폼(스팀 등 링크 같이!) :
    가격(세일 여부도 같이!) :
    플레이타임 :
    추천 이유 :
    """
    result = {
        "title": thread_title.strip(),
        "genres": [],
        "url": "",
        "manualPriceText": "",
        "playtime": "",
        "reason": "",
    }

    if not content:
        return result

    # URL 먼저 추출
    url_match = re.search(r"https?://[^\s<>)\]]+", content)
    if url_match:
        result["url"] = url_match.group(0)

    lines = content.splitlines()
    current_key = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("---"):
            continue

        if ":" in line:
            key_part, val_part = line.split(":", 1)
            key = key_part.strip()
            val = val_part.strip()

            if "게임 이름" in key:
                current_key = "title"
                if val:
                    result["title"] = val
                continue
            elif "장르" in key:
                current_key = "genres"
                if val:
                    result["genres"] = [
                        g.strip() for g in re.split(r"[,/·]+", val) if g.strip()
                    ]
                continue
            elif "플랫폼" in key:
                current_key = "url"
                link_in_val = re.search(r"https?://[^\s<>)\]]+", val)
                if link_in_val:
                    result["url"] = link_in_val.group(0)
                continue
            elif "가격" in key:
                current_key = "manualPriceText"
                if val:
                    result["manualPriceText"] = val
                continue
            elif "플레이타임" in key:
                current_key = "playtime"
                if val:
                    result["playtime"] = val
                continue
            elif "추천 이유" in key:
                current_key = "reason"
                if val:
                    result["reason"] = val
                continue

        # 줄바꿈으로 이어지는 추천 이유 본문 처리
        if current_key == "reason":
            result["reason"] = (result["reason"] + " " + line).strip()

    return result


def sync_all():
    # 기존 games.json 로드
    games_path = "games.json"
    existing_games = []
    if os.path.exists(games_path):
        with open(games_path, "r", encoding="utf-8") as f:
            existing_games = json.load(f)

    # 1. 디스코드 토큰이 설정되어 있으면 포럼 스레드 수집
    if DISCORD_BOT_TOKEN:
        print(f"[INFO] 디스코드 포럼 채널({FORUM_CHANNEL_ID}) 스캔 시작...")
        try:
            channel_info = discord_get(f"/channels/{FORUM_CHANNEL_ID}")
            available_tags = channel_info.get("available_tags", [])
            tag_map = {}
            for t in available_tags:
                emoji_name = t.get("emoji_name") or ""
                name = t.get("name", "")
                full_name = f"{emoji_name} {name}".strip() if emoji_name else name
                tag_map[t["id"]] = {"raw_name": name, "full_name": full_name}

            # 활성 스레드 + 보관된 공개 스레드 가져오기
            active_data = discord_get(f"/guilds/{GUILD_ID}/threads/active")
            threads = [
                th
                for th in active_data.get("threads", [])
                if th.get("parent_id") == FORUM_CHANNEL_ID
            ]

            try:
                archived_data = discord_get(
                    f"/channels/{FORUM_CHANNEL_ID}/threads/archived/public?limit=100"
                )
                threads.extend(archived_data.get("threads", []))
            except Exception as exc:
                print(f"[WARN] 보관된 스레드 조회 생략: {exc}")

            # 중복 스레드 제거
            unique_threads = {t["id"]: t for t in threads}.values()
            synced_from_discord = []

            for th in unique_threads:
                thread_id = th["id"]
                thread_title = th.get("name", "제목 없음")
                applied_tag_ids = th.get("applied_tags", [])

                # 태그 매핑
                genres = []
                difficulty = "보통"
                multiplayer = False
                rianfox_pick = False
                play_status = "시작 전"

                for tid in applied_tag_ids:
                    t_info = tag_map.get(tid, {})
                    rname = t_info.get("raw_name", "")
                    fname = t_info.get("full_name", "")

                    if rname in GENRE_TAG_NAMES:
                        genres.append(rname)
                    elif rname in DIFFICULTY_TAG_NAMES:
                        difficulty = rname
                    elif "멀티 가능" in rname or "멀티 가능" in fname:
                        multiplayer = True
                    elif "리안뽁스 취향" in rname or "리안뽁스 취향" in fname:
                        rianfox_pick = True
                    elif "찜 목록" in rname or "찜 목록" in fname:
                        play_status = "👀 찜 목록 추가 완료"
                    elif "플레이 예정" in rname or "플레이 중" in rname:
                        play_status = "🎮 플레이 예정/플레이 중"
                    elif "플레이 완료" in rname:
                        play_status = "✅ 플레이 완료"

                # 포럼 첫 메시지(스타터 메시지) 및 👍 반응수 조회
                votes = 1
                starter_content = ""
                created_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                try:
                    msg = discord_get(f"/channels/{thread_id}/messages/{thread_id}")
                    starter_content = msg.get("content", "")
                    if msg.get("timestamp"):
                        created_date = msg["timestamp"][:10]
                    reactions = msg.get("reactions", [])
                    if reactions:
                        votes = max(r.get("count", 1) for r in reactions)
                except Exception as exc:
                    print(f"[WARN] 스레드 메시지 조회 실패 ({thread_title}): {exc}")

                parsed = parse_guideline_message(starter_content, thread_title)
                merged_genres = list(dict.fromkeys(genres + parsed["genres"])) or ["어드벤처"]

                synced_from_discord.append(
                    {
                        "id": int(thread_id),
                        "title": parsed["title"],
                        "date": created_date,
                        "votes": votes,
                        "purchased": False,
                        "playStatus": play_status,
                        "uploadStatus": "시작 전",
                        "genres": merged_genres,
                        "difficulty": difficulty,
                        "multiplayer": multiplayer,
                        "rianfoxPick": rianfox_pick,
                        "playtime": parsed["playtime"] or "미정",
                        "regularPrice": 0,
                        "currentPrice": 0,
                        "discountPercent": 0,
                        "isOnSale": False,
                        "url": parsed["url"],
                        "reason": parsed["reason"],
                        "note": parsed["manualPriceText"],
                    }
                )
                time.sleep(0.35)

            if synced_from_discord:
                existing_games = synced_from_discord
        except Exception as exc:
            print(f"[ERROR] 디스코드 API 연동 중 오류 발생 (기존 목록 유지): {exc}")
    else:
        print("[INFO] DISCORD_BOT_TOKEN이 없어 기존 games.json의 스팀 세일 가격만 갱신합니다.")

    # 2. 모든 게임에 대해 스팀 한국 스토어(KRW) 실시간 가격 및 세일 여부 업데이트
    print(f"[INFO] 총 {len(existing_games)}개 게임의 Steam 실시간 가격/세일 조회 시작...")
    for game in existing_games:
        steam_url = game.get("url", "")
        if "store.steampowered.com/app/" in steam_url:
            steam_data = fetch_steam_price_krw(steam_url)
            if steam_data:
                game["regularPrice"] = steam_data.get("regularPrice", game.get("regularPrice", 0))
                game["currentPrice"] = steam_data.get("currentPrice", game.get("currentPrice", 0))
                game["discountPercent"] = steam_data.get("discountPercent", 0)
                game["isOnSale"] = steam_data.get("isOnSale", False)
                if steam_data.get("headerImage"):
                    game["headerImage"] = steam_data["headerImage"]
            time.sleep(0.25)

    # 저장
    with open(games_path, "w", encoding="utf-8") as f:
        json.dump(existing_games, f, ensure_ascii=False, indent=2)

    print("[SUCCESS] games.json 업데이트 완료!")


if __name__ == "__main__":
    sync_all()
