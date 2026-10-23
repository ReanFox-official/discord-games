#!/usr/bin/env python3
"""
리안뽁스 디스코드 게임 추천 포럼 + 기존 노션 목록 누적 병합 + 스팀 실시간 세일 동기화 스크립트
- 기존 노션 데이터(games.json)를 삭제하지 않고 보존하면서, 디스코드 포럼의 최신 상태와 합쳐줍니다(Merge).
- 리안뽁스 보유 여부(purchased)도 자동으로 스마트하게 판별합니다:
  1) 기존 노션 목록에서 구매 완료(O)였던 게임은 계속 O 유지
  2) 디코 태그가 '🎮 플레이 예정/플레이 중' 또는 '✅ 플레이 완료'이거나, '구매'/'보유' 태그가 붙으면 자동으로 O 처리
  3) 디코 포스트에 리안뽁스님이 🛍️(또는 🎁, 💰, 🦊) 이모지를 눌러두시면 자동으로 보유(O) 처리!
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

# 포스트에 이 이모지가 달려 있으면 '보유(구매 완료: O)'로 자동 인식!
OWNED_REACTION_EMOJIS = {"🛍️", "🎁", "💰", "🛒", "⭕"}


def normalize_title(text: str) -> str:
    """괄호나 공백, 특수문자를 제거해 같은 게임인지 비교하기 위한 정규화 함수"""
    if not text:
        return ""
    # 괄호 안 영문/한글 부제 제거 전 전체 소문자 비교용과 기본 이름 모두 활용
    cleaned = re.sub(r"[\s\-_®™:·.,!?()\[\]]+", "", text.lower())
    return cleaned


def extract_steam_appid(url: str) -> str:
    """스팀 URL에서 숫자 App ID 추출"""
    if not url:
        return ""
    m = re.search(r"store\.steampowered\.com/app/(\d+)", url)
    return m.group(1) if m else ""


def discord_get(path: str):
    """Discord REST API GET 호출"""
    url = f"{DISCORD_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
            "User-Agent": "RianfoxGameSyncBot/2.0",
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
    app_id = extract_steam_appid(steam_url)
    if not app_id:
        return {}

    api_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=kr&l=korean"
    try:
        req = urllib.request.Request(
            api_url,
            headers={"User-Agent": "Mozilla/5.0 (RianfoxGameDashboard/2.0)"},
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
    리안뽁스 게임 추천 채널 가이드라인 텍스트 파싱
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

        if current_key == "reason":
            result["reason"] = (result["reason"] + " " + line).strip()

    return result


def merge_existing_and_discord(existing_games: list, discord_games: list) -> list:
    """
    기존 노션 게임 목록(existing_games)을 절대 지우지 않고 보존하면서,
    디스코드 포럼에서 읽어온 게임(discord_games)과 스마트하게 병합(Merge)합니다.
    - 같은 스팀 App ID를 가졌거나, 게임 제목이 같으면 하나의 카드로 합쳐서 최신화합니다.
    - 디코에 없는 기존 노션 게임들은 그대로 유지됩니다.
    """
    by_id = {}
    by_appid = {}
    by_title = {}

    merged_list = []

    for idx, g in enumerate(existing_games):
        game_copy = dict(g)
        merged_list.append(game_copy)
        gid = str(game_copy.get("id", ""))
        if gid:
            by_id[gid] = idx
        appid = extract_steam_appid(game_copy.get("url", ""))
        # 아우터와일즈 모드처럼 같은 본편 링크(753640)를 공유하는 모드는 제목으로만 매칭
        if appid and appid != "753640":
            by_appid[appid] = idx
        norm_t = normalize_title(game_copy.get("title", ""))
        if norm_t:
            by_title[norm_t] = idx
            # 괄호 앞부분 한글/영문 메인 제목으로도 매칭 등록
            short_t = normalize_title(re.split(r"[(\[]", game_copy.get("title", ""))[0])
            if short_t and short_t not in by_title:
                by_title[short_t] = idx

    for dg in discord_games:
        dg_id = str(dg.get("id", ""))
        dg_appid = extract_steam_appid(dg.get("url", ""))
        dg_norm_title = normalize_title(dg.get("title", ""))
        dg_short_title = normalize_title(re.split(r"[(\[]", dg.get("title", ""))[0])

        match_idx = None
        if dg_id in by_id:
            match_idx = by_id[dg_id]
        elif dg_appid and dg_appid != "753640" and dg_appid in by_appid:
            match_idx = by_appid[dg_appid]
        elif dg_norm_title and dg_norm_title in by_title:
            match_idx = by_title[dg_norm_title]
        elif dg_short_title and dg_short_title in by_title:
            match_idx = by_title[dg_short_title]

        if match_idx is not None:
            # 기존 노션 데이터와 디스코드 포스트 병합!
            target = merged_list[match_idx]
            target["votes"] = max(int(target.get("votes", 1)), int(dg.get("votes", 1)))
            if dg.get("playStatus") and dg["playStatus"] != "시작 전":
                target["playStatus"] = dg["playStatus"]

            # 보유 여부(purchased): 기존 노션에서 O였거나, 디코에서 보유/플레이중/완료로 판별되면 O!
            target["purchased"] = bool(target.get("purchased")) or bool(dg.get("purchased"))

            # 취향 태그 및 멀티 여부
            target["rianfoxPick"] = bool(target.get("rianfoxPick")) or bool(dg.get("rianfoxPick"))
            target["multiplayer"] = bool(target.get("multiplayer")) or bool(dg.get("multiplayer"))

            # 장르 합치기
            combined_genres = list(
                dict.fromkeys((dg.get("genres") or []) + (target.get("genres") or []))
            )
            if combined_genres:
                target["genres"] = combined_genres

            if dg.get("difficulty"):
                target["difficulty"] = dg["difficulty"]
            if dg.get("url"):
                target["url"] = dg["url"]
            if dg.get("playtime") and dg["playtime"] != "미정":
                target["playtime"] = dg["playtime"]
            if dg.get("reason"):
                target["reason"] = dg["reason"]
        else:
            # 디스코드에서 새로 추천된 게임 추가
            merged_list.append(dg)

    return merged_list


def sync_all():
    games_path = "games.json"
    existing_games = []
    if os.path.exists(games_path):
        with open(games_path, "r", encoding="utf-8") as f:
            existing_games = json.load(f)

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

            unique_threads = {t["id"]: t for t in threads}.values()
            synced_from_discord = []

            for th in unique_threads:
                thread_id = th["id"]
                thread_title = th.get("name", "제목 없음")
                applied_tag_ids = th.get("applied_tags", [])

                genres = []
                difficulty = "보통"
                multiplayer = False
                rianfox_pick = False
                play_status = "시작 전"
                purchased_by_tag = False

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
                        purchased_by_tag = True  # 플레이 예정/플레이 중이면 보유(O)로 자동 처리!
                    elif "플레이 완료" in rname:
                        play_status = "✅ 플레이 완료"
                        purchased_by_tag = True  # 플레이 완료면 보유(O)로 자동 처리!

                    # 만약 포럼에 '구매 완료'나 '보유' 태그를 추가해 쓰시는 경우에도 자동 인식!
                    if "구매" in rname or "보유" in rname or "소장" in rname:
                        purchased_by_tag = True

                votes = 1
                starter_content = ""
                created_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                purchased_by_reaction = False

                try:
                    msg = discord_get(f"/channels/{thread_id}/messages/{thread_id}")
                    starter_content = msg.get("content", "")
                    if msg.get("timestamp"):
                        created_date = msg["timestamp"][:10]
                    reactions = msg.get("reactions", [])
                    if reactions:
                        votes = max(r.get("count", 1) for r in reactions)
                        for r in reactions:
                            ename = (r.get("emoji") or {}).get("name", "")
                            if ename in OWNED_REACTION_EMOJIS:
                                purchased_by_reaction = True
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
                        "purchased": purchased_by_tag or purchased_by_reaction,
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
                print(
                    f"[INFO] 기존 노션 목록({len(existing_games)}개)과 디코 포럼({len(synced_from_discord)}개) 누적 병합 중..."
                )
                existing_games = merge_existing_and_discord(
                    existing_games, synced_from_discord
                )
        except Exception as exc:
            print(f"[ERROR] 디스코드 API 연동 중 오류 발생 (기존 목록 유지): {exc}")
    else:
        print("[INFO] DISCORD_BOT_TOKEN이 없어 기존 games.json의 스팀 세일 가격만 갱신합니다.")

    # 모든 게임의 보유 여부 안전 보정: 플레이 완료 또는 플레이 중인 게임은 무조건 보유(O) 처리
    for game in existing_games:
        st = game.get("playStatus", "")
        if "플레이 완료" in st or "플레이 예정" in st or "플레이 중" in st:
            game["purchased"] = True

    # 스팀 한국 스토어(KRW) 실시간 가격 및 세일 여부 업데이트
    print(f"[INFO] 총 {len(existing_games)}개 게임의 Steam 실시간 가격/세일 조회 시작...")
    for game in existing_games:
        steam_url = game.get("url", "")
        if "store.steampowered.com/app/" in steam_url:
            steam_data = fetch_steam_price_krw(steam_url)
            if steam_data:
                game["regularPrice"] = steam_data.get(
                    "regularPrice", game.get("regularPrice", 0)
                )
                game["currentPrice"] = steam_data.get(
                    "currentPrice", game.get("currentPrice", 0)
                )
                game["discountPercent"] = steam_data.get("discountPercent", 0)
                game["isOnSale"] = steam_data.get("isOnSale", False)
                if steam_data.get("headerImage"):
                    game["headerImage"] = steam_data["headerImage"]
            time.sleep(0.25)

    # 추천수 높은 순 -> 최신순 기본 정렬 후 저장
    existing_games.sort(key=lambda x: (int(x.get("votes", 0)), str(x.get("date", ""))), reverse=True)

    with open(games_path, "w", encoding="utf-8") as f:
        json.dump(existing_games, f, ensure_ascii=False, indent=2)

    print(f"[SUCCESS] 총 {len(existing_games)}개 게임 누적 병합 및 업데이트 완료!")


if __name__ == "__main__":
    sync_all()
