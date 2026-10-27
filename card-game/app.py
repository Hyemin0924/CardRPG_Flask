from builtins import len

from flask import Flask, render_template, jsonify, request
import random
import math
import logging

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("game_logger")

def log_event(level, room_id, action, player_id=None, target_id=None, details=None, error=None):
    log_parts = []
    if room_id:
        log_parts.append(f"room={room_id}")
    if player_id is not None:
        log_parts.append(f"player={player_id}")
    if target_id is not None:
        log_parts.append(f"target={target_id}")
    log_parts.append(f"action={action}")
    if details:
        log_parts.append(f"details={details}")
    if error:
        log_parts.append(f"error={error}")

    msg = " | ".join(log_parts)
    
    if level == "INFO":
        logger.info(msg)
    elif level == "WARNING":
        logger.warning(msg)
    elif level == "ERROR":
        logger.error(msg)
MAX_ROUNDS = 3
MIN_CARDS_PER_TURN = 2
MAX_CARDS_PER_TURN = 3

# 보스전 포지션 (직업)
JOBS = ["탱커", "딜러", "서포터", "힐러"]


CARD_DATA = [
    {
        "name": "덤벨",
        "type": "성장",
        "text": "공격력 +2",
        "count": 2
    },
    {
        "name": "검술훈련",
        "type": "성장",
        "text": "주사위 (1-3: 공격력+1, 4-6: 공격력+2)",
        "count": 2
    },
    {
        "name": "책읽기",
        "type": "성장",
        "text": "지능 +2",
        "count": 2
    },
    {
        "name": "마법연구",
        "type": "성장",
        "text": "주사위 (1-3: 지능+1, 4-6: 지능+2)",
        "count": 2
    },
    {
        "name": "수영",
        "type": "성장",
        "text": "체력 +3",
        "count": 2
    },
    {
        "name": "등산",
        "type": "성장",
        "text": "체력 +2",
        "count": 2
    },
    {
        "name": "검",
        "type": "장비",
        "text": "공격력 ×1.1",
        "count": 1
    },
    {
        "name": "가죽 갑옷",
        "type": "장비",
        "text": "방어력 ×1.05",
        "count": 1
    },
    {
        "name": "철 갑옷",
        "type": "장비",
        "text": "방어력 ×1.1",
        "count": 1
    },
    {
        "name": "금 갑옷",
        "type": "장비",
        "text": "방어력 ×1.15",
        "count": 1
    },
    {
        "name": "다이아 갑옷",
        "type": "장비",
        "text": "방어력 ×1.2",
        "count": 1
    },
    {
        "name": "은반지",
        "type": "장비",
        "text": "지력 ×1.05",
        "count": 1
    },
    {
        "name": "금반지",
        "type": "장비",
        "text": "지력 ×1.1",
        "count": 1
    },
    {
        "name": "전우의 격려",
        "type": "협력",
        "text": "자신: 체력+4 / 동료: 경험치+1",
        "count": 3
    },
    {
        "name": "마법 조언",
        "type": "협력",
        "text": "자신: 지력+4 / 동료: 경험치+1",
        "count": 3
    },
    {
        "name": "훈련 지원",
        "type": "협력",
        "text": "자신: 공격력+4 / 동료: 경험치+1",
        "count": 3
    },
    {
        "name": "칭찬",
        "type": "협력",
        "text": "자신: 정신력+1 / 동료: 경험치+1",
        "count": 3
    },
    {
        "name": "게으름",
        "type": "딜레마",
        "text": "손패 카드 1장 제거",
        "count": 2
    },
    {
        "name": "질병",
        "type": "딜레마",
        "text": "다음 턴 경험치 획득 불가",
        "count": 1
    },
    {
        "name": "질투",
        "type": "딜레마",
        "text": "다음 턴 자신에게 협력카드 사용 불가",
        "count": 1
    },
    {
        "name": "욕심",
        "type": "딜레마",
        "text": "다음 턴 동료에게 협력카드 사용 불가",
        "count": 1
    },
    {
        "name": "분열",
        "type": "딜레마",
        "text": "다음 턴 모든 플레이어 협력카드 사용 금지",
        "count": 1
    },
    {
        "name": "민폐",
        "type": "딜레마",
        "text": "다른 플레이어 손패/장비 1개 제거",
        "count": 1
    },
    {
        "name": "부상",
        "type": "딜레마",
        "text": "본인: 랜덤 스탯-4 / 타인: 랜덤 스탯-3",
        "count": 1
    },
    {
        "name": "인내심 폭발",
        "type": "딜레마",
        "text": "본인: 정신력-1 / 타인: 랜덤 스탯-1",
        "count": 1
    }
]
TARGETED_CARDS = ["전우의 격려", "마법 조언", "훈련 지원", "칭찬", "게으름", "민폐", "부상", "인내심 폭발"]

import string

# 장비 슬롯/등급/배율 정보: 같은 슬롯(무기/갑옷/반지)은 가장 좋은 등급 하나만 장착됨
# mult: 보스전 시작 시 적용되는 배율 (무기→공격력, 반지→지능, 갑옷→받는 피해 감소용 나눗값)
EQUIPMENT_INFO = {
    "검": {"slot": "무기", "tier": 1, "mult": 1.1},
    "가죽 갑옷": {"slot": "갑옷", "tier": 1, "mult": 1.05},
    "철 갑옷": {"slot": "갑옷", "tier": 2, "mult": 1.1},
    "금 갑옷": {"slot": "갑옷", "tier": 3, "mult": 1.15},
    "다이아 갑옷": {"slot": "갑옷", "tier": 4, "mult": 1.2},
    "은반지": {"slot": "반지", "tier": 1, "mult": 1.05},
    "금반지": {"slot": "반지", "tier": 2, "mult": 1.1},
}


def get_equipment_multiplier(player, slot):
    # 해당 슬롯에 장착된 장비의 배율을 반환 (없으면 1.0)
    for eq in player["equipment"]:
        info = EQUIPMENT_INFO.get(eq["name"])
        if info and info["slot"] == slot:
            return info["mult"]
    return 1.0

# room_id -> game state 딕셔너리 (서버 하나에서 여러 방을 동시에 관리)
games = {}


def create_new_game_state():
    return {
        "started": False,
        "max_players": 0,
        "round": 0,
        "max_rounds": MAX_ROUNDS,
        "deck": [],
        "players": [],
        "message": "",
        "game_over": False,

        # 전체 협력카드 사용 금지 (다음 턴부터 적용)
        "split": False,
        # 분열 카드를 사용해서 다음 턴부터 적용될 예정인 상태
        "split_pending": False
    }


def generate_room_id():
    while True:
        room_id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if room_id not in games:
            return room_id


def get_state_or_404(room_id):
    state = games.get(room_id)
    if state is None:
        log_event("WARNING", room_id=room_id, action="GET_STATE", error="ROOM_NOT_FOUND")
        return None, (jsonify({
            "success": False,
            "message": "존재하지 않는 방입니다."
        }), 404)
    return state, None


def start_new_turn_cycle(state):
    # 모든 플레이어가 함께 턴을 소모하는 구조이므로, "모두"가 턴을 종료해야
    # 다음 턴 사이클이 시작된다. 질투/질병/분열/욕심 전부 카드 텍스트 그대로
    # "다음 턴부터" 적용되는 효과이므로, 이번에 예약(pending)되어 있던 값을
    # 활성(active) 값으로 승격시키고, 활성화되어 있던 이전 값(지난 턴 몫)은
    # 여기서 해제된다.
    for p in state["players"]:
        p["turn_ended"] = False
        p["used_cards_this_turn"] = 0

        p["jealousy"] = p.get("jealousy_pending", False)
        p["jealousy_pending"] = False

        p["sick"] = p.get("sick_pending", False)
        p["sick_pending"] = False

        p["greed_next_turn"] = p.get("greed_pending", False)
        p["greed_pending"] = False

    state["split"] = state.get("split_pending", False)
    state["split_pending"] = False


def get_required_cooperation_count(state):

    player_count = state["max_players"]

    if player_count == 2:
        return 5

    elif player_count == 3:
        return 3

    elif player_count == 4:
        return 2

    return 5

def add_experience(state, player, amount):
    player["experience"] += amount
    required_exp = get_required_cooperation_count(state)

    leveled_up = False
    while player["experience"] >= required_exp:
        player["experience"] -= required_exp
        player["level"] += 1
        leveled_up = True

    return leveled_up

def create_deck():
    deck = []

    for card in CARD_DATA:
        for _ in range(card["count"]):
            deck.append(card.copy())

    random.shuffle(deck)

    return deck


def draw_card(state):
    if not state["deck"]:
        return None

    return state["deck"].pop()

def apply_self_cooperation_effect(player, name):
    # 협력 카드를 자기 자신에게 사용했을 때의 효과
    if name == "전우의 격려":
        player["stats"]["hp"] += 4
    elif name == "마법 조언":
        player["stats"]["intelligence"] += 4
    elif name == "훈련 지원":
        player["stats"]["attack"] += 4
    elif name == "칭찬":
        player["stats"]["mental"] += 1


def apply_target_card_effect(
    state,
    sender,
    target,
    card
):

    name =card["name"]

    # 협력 카드는 _resolve_target_card_use()에서 이미 별도로 처리되어
    # 이 함수까지 협력 카드가 넘어오는 경우가 없다. (과거 이 자리에 있던
    # 협력 카드 처리 로직은 실제로는 절대 호출되지 않는 중복 코드였기 때문에 제거함)

    # =================
    # 게으름
    # =================
    if name == "게으름":
        removable_hand_cards = [c for c in target["hand"] if c["type"] != "딜레마"]

        # 1순위: 손패 카드 제거
        if removable_hand_cards:
            removed_card = random.choice(removable_hand_cards)
            target["hand"].remove(removed_card)

            replacement = draw_card(state)
            redraw_msg = ""
            if replacement:
                target["hand"].append(replacement)
                redraw_msg = f" {target['name']}이(가) 새 카드를 뽑았습니다."

            return f"{sender['name']}이(가) {target['name']}의 손패 '{removed_card['name']}' 카드를 제거했습니다." + redraw_msg

        # 2순위: 손패에 없으면 장착 중인 장비 제거
        elif target["equipment"]:
            removed_eq = random.choice(target["equipment"])
            target["equipment"].remove(removed_eq)
            return f"{sender['name']}이(가) {target['name']}의 장착 장비 '{removed_eq['name']}'을(를) 제거했습니다."

        # 3순위: 손패도 장비도 모두 없으면 효과 없이 소멸
        else:
            return f"{target['name']}에게 제거 가능한 손패나 장비가 없어 게으름 카드가 효과 없이 소멸했습니다."

        


    # =================
    # 민폐
    # =================

    if name == "민폐":
        possible_items = [{"type": "hand", "item": c} for c in target["hand"]] + \
                         [{"type": "equipment", "item": eq} for eq in target["equipment"]]

        if not possible_items:
            return "모든 플레이어에게 제거 가능한 카드/장비가 없어 민폐 카드가 효과 없이 소멸했습니다."

        removed = random.choice(possible_items)
        redraw_msg = ""

        if removed["type"] == "hand":
            target["hand"].remove(removed["item"])
            replacement = draw_card(state)
            if replacement:
                target["hand"].append(replacement)
                redraw_msg = f" {target['name']}이(가) 새 카드를 뽑았습니다."
        else:
            target["equipment"].remove(removed["item"])

        return f"{sender['name']}이(가) {target['name']}의 '{removed['item']['name']}'을(를) 제거했습니다." + redraw_msg


    # =================
    # 부상
    # =================

    if name == "부상":

        stat_names = [

            "hp",
            "attack",
            "intelligence"

        ]


        if (
            sender["id"]
            == target["id"]
        ):

            selected_stat =random.choice(
                    stat_names
                )

            damage = 4


        else:

            selected_stat =random.choice(
                    stat_names
                )

            damage = 3


        target[
            "stats"
        ][
            selected_stat
        ] -= damage


        return (
            f"{target['name']}의 "
            f"{selected_stat} "
            f"-{damage}"
        )


    # =================
    # 인내심 폭발
    # =================

    if name == "인내심 폭발":

        if (
            sender["id"]
            == target["id"]
        ):

            target[
                "stats"
            ][
                "mental"
            ] -= 1


            return (
                f"{target['name']}의 "
                "정신력 -1"
            )


        stat_names = [

            "hp",
            "attack",
            "intelligence",
            "mental"

        ]


        selected_stat =random.choice(
                stat_names
            )


        target[
            "stats"
        ][
            selected_stat
        ] -= 1


        return (
            f"{target['name']}의 "
            f"{selected_stat} -1"
        )


    return (
        "카드 효과가 적용되었습니다."
    )
def get_active_players(state):
    return [p for p in state["players"] if p["connected"] and not p.get("eliminated", False)]
def create_player(player_id, job=None):
    return {
        "id": player_id,
        "name": f"플레이어 {player_id}",
        "connected": False,
        "level": 1,
        "experience": 0,
        "eliminated": False,
        # 보스전에서 사용할 포지션 (탱커/딜러/서포터/힐러)
        "job": job,

        "stats": {
            "hp": 1,
            "attack": 1,
            "intelligence": 1,
            "mental": 1
        },

        "hand": [],
        "equipment": [],

        "used_cards_this_turn": 0,
        "turn_ended": False,

        # 다음 턴 자신에게 협력카드 사용 불가 (현재 턴에 활성화되는 값)
        "jealousy": False,
        # 질투 카드를 사용해서 다음 턴부터 적용될 예정인 상태
        "jealousy_pending": False,

        # 다음 턴 동료에게 협력카드 사용 불가 (현재 턴에 활성화되는 값)
        "greed_next_turn": False,
        # 욕심 카드를 사용해서 다음 턴부터 적용될 예정인 상태
        "greed_pending": False,

        # 다음 턴 경험치 획득 불가 (현재 턴에 활성화되는 값)
        "sick": False,
        # 질병 카드를 사용해서 다음 턴부터 적용될 예정인 상태
        "sick_pending": False
    }


def get_public_state(state, my_player_id=None):
    players = []

    for player in state["players"]:
        public_player = {
            "id": player["id"],
            "name": player["name"],
            "connected": player["connected"],
            "level": player["level"],
            "eliminated": player.get("eliminated", False),
            "job": player.get("job"),
            "stats": player["stats"],
            "equipment": player["equipment"],
            "experience": player.get(
                "experience",
                0
            ),
            "used_cards_this_turn": player["used_cards_this_turn"],
            "turn_ended": player["turn_ended"],
            "jealousy": player.get(
                "jealousy",
                False
            ),
            "jealousy_pending": player.get(
                "jealousy_pending",
                False
            ),
            "greed_next_turn": player.get(
                "greed_next_turn",
                False
            ),
            "greed_pending": player.get(
                "greed_pending",
                False
            ),
            "sick": player.get(
                "sick",
                False
            ),
            "sick_pending": player.get(
                "sick_pending",
                False
            )
        }

        # 내 플레이어일 때만 손패 공개
        if player["id"] == my_player_id:
            public_player["hand"] = player["hand"]
        else:
            public_player["hand_count"] = len(player["hand"])

        players.append(public_player)

    return {
        "started": state["started"],
        "max_players": state["max_players"],
        "round": state["round"],
        "max_rounds": state["max_rounds"],
        "deck_count": len(state["deck"]),
        "players": players,
        "message": state["message"],
        "game_over": state["game_over"],
        "split": state["split"],
        "split_pending": state.get("split_pending", False),

        # 보스전 상태
        "boss_active": state.get("boss_active", False),
        "boss": state.get("boss"),
        "boss_turn": state.get("boss_turn"),
        "boss_log": state.get("boss_log", []),
        "boss_party": state.get("boss_party", []),
        "boss_result": state.get("boss_result"),

        # game_over는 "라운드가 모두 끝나 보스전에 진입 가능한 상태"를 의미하며,
        # 보스전 승패가 갈리기 전(진행 중)에도 True다. 게임 전체(보스전 포함)가
        # 실제로 끝났는지는 이 필드로 명확히 구분한다.
        "game_finished": state.get("boss_result") is not None
    }


@app.route("/")
def index():
    return render_template("index.html")


# 방 생성
@app.route("/api/game/create", methods=["POST"])
def create_game():
    data = request.get_json()
    player_count = data.get("player_count")
    creator_job = data.get("job")

    if creator_job not in JOBS:
        creator_job = "탱커"

    if not player_count or player_count < 1 or player_count > 4:
        return jsonify({
            "success": False,
            "message": "플레이어 수는 1~4명이어야 합니다."
        }), 400

    room_id = generate_room_id()
    state = create_new_game_state()
    games[room_id] = state

    state["started"] = True
    state["max_players"] = player_count
    state["round"] = 1
    state["deck"] = create_deck()
    state["players"] = []
    state["message"] = "방이 생성되었습니다."
    state["game_over"] = False

    for i in range(player_count):

        # 방장(플레이어 1)만 이 시점에 직업이 정해지고,
        # 나머지는 각자 참가(join)할 때 직업을 선택함
        job = creator_job if i == 0 else None

        player = create_player(i + 1, job)

        for _ in range(5):

            card = draw_card(state)

            if card:
                player["hand"].append(card)

        state["players"].append(player)

    # 방을 만든 사람(플레이어 1)은 이미 접속한 상태로 표시
    state["players"][0]["connected"] = True

    return jsonify({
        "success": True,
        "room_id": room_id,
        "player_id": 1,
        "state": get_public_state(state, 1)
    })


# 플레이어 참가
@app.route("/api/game/join", methods=["POST"])
def join_game():

    data = request.get_json()
    room_id = data.get("room_id")
    job = data.get("job")

    if job not in JOBS:
        log_event("WARNING", room_id=room_id, action="JOIN_ROOM", details=f"job={job}", error="INVALID_JOB")
        return jsonify({
            "success": False,
            "message": "올바른 직업(탱커, 딜러, 서포터, 힐러)을 선택해주세요."
        }), 400

    state, error = get_state_or_404(room_id)
    if error:
        return error

    if not state["started"]:
        log_event("WARNING", room_id=room_id, action="JOIN_ROOM", error="GAME_NOT_STARTED")
        return jsonify({
            "success": False,
            "message": "아직 생성된 게임이 없습니다."
        }), 400
    taken_jobs = [p["job"] for p in state["players"] if p["connected"] and p.get("job")]
    if job in taken_jobs:
        log_event("WARNING", room_id=room_id, action="JOIN_ROOM", details=f"job={job}", error="JOB_ALREADY_TAKEN")
        return jsonify({
            "success": False,
            "message": f"'{job}' 직업은 이미 다른 플레이어가 선택했습니다."
        }), 400

    for player in state["players"]:

        if not player["connected"]:

            player["connected"] = True
            player["job"] = job
            log_event("INFO", room_id=room_id, player_id=player["id"], action="JOIN_ROOM", details=f"job={job}")
            return jsonify({
                "success": True,
                "player_id": player["id"],
                "state": get_public_state(state, player["id"])
            })
    log_event("WARNING", room_id=room_id, action="JOIN_ROOM", error="ROOM_FULL")
    return jsonify({
        "success": False,
        "message": "모든 플레이어가 이미 참가했습니다."
    }), 400


# 게임 상태 조회
@app.route("/api/game/state", methods=["GET"])
def get_state():

    room_id = request.args.get("room_id")
    player_id = request.args.get("player_id", type=int)

    state, error = get_state_or_404(room_id)
    if error:
        return error

    return jsonify({
        "success": True,
        "state": get_public_state(state, player_id)
    })
def _resolve_target_card_use(state, room_id,sender_id, target_id, card_index, allowed_types=None):
    sender = next((p for p in state["players"] if p["id"] == sender_id), None)
    target = next((p for p in state["players"] if p["id"] == target_id), None)

    if sender is None or target is None:
        log_event("WARNING", room_id=room_id, action="USE_TARGET_CARD", error="INVALID_PLAYER_TARGET")
        return None, (jsonify({"success": False, "message": "플레이어 대상 정보가 올바르지 않습니다."}), 400)

    if sender["turn_ended"]:
        log_event("WARNING", room_id=room_id, action="USE_TARGET_CARD", error="TURN_ALREADY_ENDED")
        return None, (jsonify({"success": False, "message": "이미 턴을 종료했습니다."}), 400)

    if sender["used_cards_this_turn"] >= MAX_CARDS_PER_TURN:
        log_event("WARNING", room_id=room_id, action="USE_TARGET_CARD", error="MAX_CARDS_EXCEEDED")
        return None, (jsonify({"success": False, "message": f"한 턴에 최대 {MAX_CARDS_PER_TURN}장까지 사용할 수 있습니다."}), 400)

    if card_index is None or card_index < 0 or card_index >= len(sender["hand"]):
        log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card_index={card_index}", error="INVALID_CARD_INDEX")        
        return None, (jsonify({"success": False, "message": "잘못된 카드 선택입니다."}), 400)
    card = sender["hand"][card_index]
    card_name = card.get("name", "Unknown")
    is_cooperation = (card["type"] == "협력")

    # 이 경로(협력 전용 / 협력+딜레마 등)로 허용되지 않는 카드 타입인지 검증
    if allowed_types is not None and card["type"] not in allowed_types:
        log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="CARD_TYPE_NOT_ALLOWED")
        return None, (jsonify({"success": False, "message": "이 카드는 이 방식으로 사용할 수 없습니다."}), 400)

    # 협력 카드 제약 조건 검증
    if is_cooperation:
        if state["split"]:
            log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="RESTRICTED_BY_SPLIT")
            return None, (jsonify({"success": False, "message": "분열의 효과로 이번 턴 협력카드를 사용할 수 없습니다."}), 400)
        if sender_id == target_id and sender.get("jealousy", False):
            log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="RESTRICTED_BY_JEALOUSY")
            return None, (jsonify({"success": False, "message": "질투의 효과로 이번 턴 자신에게 협력카드를 사용할 수 없습니다."}), 400)
        if sender_id != target_id and sender.get("greed_next_turn", False):
            log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="RESTRICTED_BY_GREED")
            return None, (jsonify({"success": False, "message": "욕심의 효과로 이번 턴 동료에게 협력카드를 사용할 수 없습니다."}), 400)

    # 민폐 카드 전용 검증 — 반드시 카드를 손패에서 제거하기 전에 확인해야
    # 검증 실패 시 카드가 사라지지 않는다
    if card_name == "민폐":
        if sender_id == target_id:
            log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="SELF_TARGET_NOT_ALLOWED")
            return None, (jsonify({"success": False, "message": "민폐 카드는 자신에게 사용할 수 없습니다."}), 400)

        target_has_items = bool(target["hand"] or target["equipment"])
        if not target_has_items:
            # 다른 타인 플레이어들 중 제거 가능한 카드가 있는 사람이 있는지 확인
            other_player_has_items = any(
                p["id"] != sender_id and (p["hand"] or p["equipment"])
                for p in state["players"]
                if p["connected"]
            )
            # 다른 플레이어에게 제거 가능한 항목이 남아있다면 대상을 다시 고르도록 튕겨냄
            if other_player_has_items:
                log_event("WARNING", room_id=room_id, player_id=sender_id, target_id=target_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="TARGET_HAS_NO_ITEMS_TRY_OTHER")
                return None, (jsonify({
                    "success": False,
                    "message": f"'{target['name']}'에게 제거 가능한 카드/장비가 없습니다. 다른 플레이어를 선택해주세요."
                }), 400)

    # 게으름 카드 전용 검증 — 자신에게만 사용 가능
    # 민폐 카드와 마찬가지로, 반드시 카드를 손패에서 제거하기 전에 확인해야
    # 검증 실패 시 카드가 사라지지 않는다
    if card_name == "게으름":
        if sender_id != target_id:
            log_event("WARNING", room_id=room_id, player_id=sender_id, action="USE_TARGET_CARD", details=f"card={card_name}", error="ONLY_SELF_TARGET_ALLOWED")
            return None, (jsonify({"success": False, "message": "게으름 카드는 자신에게만 사용할 수 있습니다."}), 400)

    # 모든 검증을 통과했을 때만 카드를 손패에서 제거 (한 번만)
    used_card = sender["hand"].pop(card_index)

    if is_cooperation:
        if sender_id == target_id:
            apply_self_cooperation_effect(target, used_card["name"])
            message = f"{target['name']}에게 {used_card['name']} 사용"
        else:
            if target.get("sick", False):
                message = f"{sender['name']}이(가) {target['name']}에게 {used_card['name']} 사용 → 질병으로 경험치 획득 불가"
            else:
                level_up_ready = add_experience(state, target, 1)
                message = f"{sender['name']}이(가) {target['name']}에게 {used_card['name']} 사용 → 경험치 +1"
                if level_up_ready:
                    message += " → 레벨업 조건 달성"
    else:
        message = apply_target_card_effect(state, sender, target, used_card)
    sender["used_cards_this_turn"] += 1

    new_card = draw_card(state)
    if new_card:
        sender["hand"].append(new_card)
        message += " 새 카드를 뽑았습니다."
    else:
        message += " 덱이 모두 소진되었습니다."
    log_event("INFO", room_id=room_id, player_id=sender_id, target_id=target_id, action="USE_TARGET_CARD", details=f"card={card_name} | result={message}")
    state["message"] = message
    return jsonify({"success": True, "state": get_public_state(state, sender_id)}), None


@app.route("/api/game/card/cooperation", methods=["POST"])
def use_cooperation_card():

    data = request.get_json()

    room_id = data.get("room_id")
    sender_id = data.get("sender_id")
    target_id = data.get("target_id")
    card_index = data.get("card_index")

    state, error = get_state_or_404(room_id)
    if error:
        return error

    # 협력 카드뿐 아니라, 실수로 대상 지정형 딜레마 카드가 이 경로로
    # 들어오더라도 정상적으로 처리되도록 두 타입 모두 허용한다.
    response, error = _resolve_target_card_use(
        state, room_id,sender_id, target_id, card_index,
        allowed_types=["협력", "딜레마"]
    )

    if error:
        return error

    return response

# 카드 사용
@app.route("/api/game/card/use", methods=["POST"])
def use_card():
    data = request.get_json()

    room_id = data.get("room_id")
    player_id = data.get("player_id")
    card_index = data.get("card_index")

    state, error = get_state_or_404(room_id)
    if error:
        return error

    player = next(
        (
            player for player in state["players"]
            if player["id"] == player_id
        ),
        None
    )

    if player is None:
        return jsonify({
            "success": False,
            "message": "플레이어를 찾을 수 없습니다."
        }), 404

    if player.get("eliminated", False):
        return jsonify({
            "success": False,
            "message": "탈락한 플레이어는 행동할 수 없습니다."
        }), 400

    if player["turn_ended"]:

        return jsonify({
            "success": False,
            "message": "이미 턴을 종료했습니다."
        }), 400

    if player["used_cards_this_turn"] >= MAX_CARDS_PER_TURN:

        return jsonify({
            "success": False,
            "message": "한 턴에 최대 3장까지 사용할 수 있습니다."
        }), 400

    if card_index < 0 or card_index >= len(player["hand"]):

        return jsonify({
            "success": False,
            "message": "잘못된 카드입니다."
        }), 400

    used_card = player["hand"].pop(card_index)

    message = apply_card_effect(state, player, used_card)

    player["used_cards_this_turn"] += 1

    # 덱이 남아 있을 때만 보충
    new_card = draw_card(state)

    if new_card:
        player["hand"].append(new_card)

        message += " 새 카드 1장을 뽑았습니다."

    else:
        message += " 덱이 모두 소진되었습니다."

    state["message"] = (
        f"플레이어 {player_id}: "
        f"{used_card['name']} 사용 - {message}"
    )

    return jsonify({
        "success": True,
        "state": get_public_state(state, player_id)
    })

def refill_hands(state, hand_size=5):
    for player in state["players"]:
        if not player["connected"] or player.get("eliminated", False):
            continue
        while len(player["hand"]) < hand_size and state["deck"]:
            player["hand"].append(draw_card(state))

def apply_card_effect(state, player, card):

    name = card["name"]

    if name == "덤벨":

        player["stats"]["attack"] += 2

        return "공격력 +2"

    elif name == "검술훈련":

        dice = random.randint(1, 6)

        if dice <= 3:
            player["stats"]["attack"] += 1
            return f"주사위 {dice} → 공격력 +1"

        player["stats"]["attack"] += 2

        return f"주사위 {dice} → 공격력 +2"

    elif name == "책읽기":

        player["stats"]["intelligence"] += 2

        return "지능 +2"

    elif name == "마법연구":

        dice = random.randint(1, 6)

        if dice <= 3:
            player["stats"]["intelligence"] += 1
            return f"주사위 {dice} → 지능 +1"

        player["stats"]["intelligence"] += 2

        return f"주사위 {dice} → 지능 +2"

    elif name == "수영":

        player["stats"]["hp"] += 3

        return "체력 +3"

    elif name == "등산":

        player["stats"]["hp"] += 2

        return "체력 +2"

    elif card["type"] == "장비":

        info = EQUIPMENT_INFO.get(name)

        if not info:
            player["equipment"].append(card)
            return "장비를 장착했습니다."

        slot = info["slot"]
        tier = info["tier"]

        existing = None
        for eq in player["equipment"]:
            eq_info = EQUIPMENT_INFO.get(eq["name"])
            if eq_info and eq_info["slot"] == slot:
                existing = eq
                break

        if existing is None:
            player["equipment"].append(card)
            return "장비를 장착했습니다."

        existing_info = EQUIPMENT_INFO.get(existing["name"])

        if existing_info["tier"] >= tier:
            return (
                f"이미 더 좋은 {slot} 장비"
                f"({existing['name']})를 장착 중이라 "
                "카드가 사라졌습니다."
            )

        player["equipment"].remove(existing)
        player["equipment"].append(card)

        return f"{existing['name']} 대신 {name}을(를) 장착했습니다."
    elif name == "질투":

        player["jealousy_pending"] = True

        return (
            "다음 턴 자신에게 "
            "협력카드를 사용할 수 없습니다."
        )


    elif name == "욕심":

        # 이번 턴이 아니라 "다음 턴"에 적용되어야 하므로 대기 상태로 표시
        player["greed_pending"] = True

        return (
            "다음 턴 동료에게 "
            "협력카드를 사용할 수 없습니다."
        )


    elif name == "분열":

        state["split_pending"] = True

        return (
            "다음 턴 모든 플레이어가 "
            "협력카드를 사용할 수 없습니다."
        )


    elif name == "질병":

        player["sick_pending"] = True

        return (
            "다음 턴 경험치를 "
            "획득할 수 없습니다."
        )

    return "카드 효과가 적용되었습니다."
@app.route(
    "/api/game/card/target",
    methods=["POST"]
)
def use_target_card():
    data = request.get_json()

    room_id = data.get("room_id")
    sender_id = data.get("sender_id")
    target_id = data.get("target_id")
    card_index = data.get("card_index")

    state, error = get_state_or_404(room_id)
    if error:
        return error

    sender = next((p for p in state["players"] if p["id"] == sender_id), None)
    if sender is not None and sender.get("eliminated", False):
        return jsonify({"success": False, "message": "탈락한 플레이어는 행동할 수 없습니다."}), 400

    # 협력 카드와 딜레마 카드 모두 이 경로로 들어올 수 있으므로 둘 다 허용한다.
    # (협력 카드는 분열/질투/욕심 제약도 여기서 동일하게 검증된다.)
    response, error = _resolve_target_card_use(
        state, room_id,sender_id, target_id, card_index,
        allowed_types=["협력", "딜레마"]
    )

    if error:
        return error

    return response

# 플레이어가 턴 종료
@app.route("/api/game/turn/end", methods=["POST"])
def end_turn():

    data = request.get_json()

    room_id = data.get("room_id")
    player_id = data.get("player_id")

    state, error = get_state_or_404(room_id)
    if error:
        return error

    player = next(
        (
            player for player in state["players"]
            if player["id"] == player_id
        ),
        None
    )

    if player is None:
        log_event("WARNING", room_id=room_id, player_id=player_id, action="TURN_END", error="PLAYER_NOT_FOUND")
        return jsonify({
            "success": False,
            "message": "플레이어를 찾을 수 없습니다."
        }), 404

    if player.get("eliminated", False):
        return jsonify({
            "success": False,
            "message": "탈락한 플레이어는 행동할 수 없습니다."
        }), 400

    # 덱이 모두 소진되었거나(더 뽑을 카드가 없음) 손패를 전부 사용한 경우에는
    # 최소 사용 장수 제한을 완화한다.
    deck_empty = not state["deck"]
    hand_empty = not player["hand"]
    connected_players = get_active_players(state)
    has_empty_hand_player = any(len(p["hand"]) == 0 for p in connected_players)
    has_cards_player = any(len(p["hand"]) > 0 for p in connected_players)
    can_end_turn = False
    error_msg = ""
    if hand_empty:
        can_end_turn = True
    elif deck_empty:
        if has_empty_hand_player and has_cards_player:
            can_end_turn = False
            error_msg = "덱이 소진되었고 손패가 떨어진 플레이어가 있으므로, 남은 카드를 모두 사용해야 턴을 종료할 수 있습니다."
        else:
            if player["used_cards_this_turn"] >= 1:
                can_end_turn = True
            else:
                error_msg = "최소 1장의 카드를 사용해야 합니다."
    else:
        if player["used_cards_this_turn"] >= MIN_CARDS_PER_TURN:
            can_end_turn = True
        else:
            error_msg = f"최소 {MIN_CARDS_PER_TURN}장의 카드를 사용해야 합니다."

    if not can_end_turn:
        log_event("WARNING", room_id=room_id, player_id=player_id, action="TURN_END", error=error_msg)
        return jsonify({"success": False, "message": error_msg}), 400

    player["turn_ended"] = True
    log_event("INFO", room_id=room_id, player_id=player_id, action="TURN_END")

    all_players_ended = all(p["turn_ended"] for p in connected_players)

    if not all_players_ended:
        state["message"] = f"플레이어 {player_id}가 턴을 종료했습니다."
        return jsonify({
            "success": True,
            "waiting": True,
            "boss_battle": False,
            "state": get_public_state(state, player_id)
        })

    if state["deck"]:
        start_new_turn_cycle(state)
        state["message"] = f"{state['round']}라운드를 계속합니다."
        log_event("INFO", room_id=room_id, action="EVENT_NEW_TURN_CYCLE", details=f"round={state['round']}")
        return jsonify({
            "success": True,
            "waiting": False,
            "boss_battle": False,
            "state": get_public_state(state, player_id)
        })

    # 덱은 비었지만 아직 손패가 남은 플레이어가 있다면, 그 카드를 모두 쓸
    # 때까지는 다음 라운드로 넘기지 않고 같은 라운드를 유지한다.
    has_remaining_hand = any(len(p["hand"]) > 0 for p in connected_players)

    if has_remaining_hand:
        start_new_turn_cycle(state)
        state["message"] = f"덱이 소진되었습니다. 남은 손패를 모두 사용할 때까지 {state['round']}라운드를 계속합니다."
        log_event("INFO", room_id=room_id, action="EVENT_NEW_TURN_CYCLE_DECK_EMPTY", details=f"round={state['round']}")
        return jsonify({
            "success": True,
            "waiting": False,
            "boss_battle": False,
            "state": get_public_state(state, player_id)
        })

    current_round = state["round"]

    if current_round >= state["max_rounds"]:
        required_level = current_round + 1
        eliminated_now = []
        for p in get_active_players(state):
            if p["level"] < required_level:
                p["eliminated"] = True
                eliminated_now.append(p["name"])
                log_event("INFO", room_id=room_id, player_id=p["id"], action="PLAYER_ELIMINATED",
                           details=f"required_level={required_level} level={p['level']}")

        state["game_over"] = True
        state["message"] = (
            f"{state['max_rounds']}라운드가 종료되었습니다. 보스전입니다. (탈락: {', '.join(eliminated_now)})"
            if eliminated_now else
            f"{state['max_rounds']}라운드가 종료되었습니다. 보스전입니다."
        )
        log_event("INFO", room_id=room_id, action="EVENT_BOSS_BATTLE_START", details=f"round={current_round}")
        return jsonify({
            "success": True,
            "waiting": False,
            "boss_battle": True,
            "state": get_public_state(state, player_id)
        })

    next_round = current_round + 1
    required_level = next_round
    eliminated_now = []
    for p in get_active_players(state):
        if p["level"] < required_level:
            p["eliminated"] = True
            eliminated_now.append(p["name"])
            log_event("INFO", room_id=room_id, player_id=p["id"], action="PLAYER_ELIMINATED",
                       details=f"round={next_round} required_level={required_level} level={p['level']}")

    # 이번 탈락 처리로 남은 활성 플레이어가 아무도 없다면, 더 이상 그 누구도
    # end_turn을 호출할 수 없어 라운드가 영원히 멈추게 된다(막다른 상태).
    # 이 경우 다음 라운드로 넘기지 않고 즉시 게임을 종료(패배)시켜
    # 보스전 진입(및 전원 탈락으로 인한 자동 패배 처리)이 가능하도록 한다.
    if not get_active_players(state):
        state["game_over"] = True
        state["message"] = (
            f"모든 플레이어가 레벨 미달로 탈락했습니다. (탈락: {', '.join(eliminated_now)})"
        )
        log_event("INFO", room_id=room_id, action="EVENT_ALL_PLAYERS_ELIMINATED", details=f"round={next_round}")
        return jsonify({
            "success": True,
            "waiting": False,
            "boss_battle": True,
            "state": get_public_state(state, player_id)
        })

    state["round"] = next_round
    state["deck"] = create_deck()
    start_new_turn_cycle(state)
    refill_hands(state)
    state["message"] = (
        f"{state['round']}라운드가 시작되었습니다. (탈락: {', '.join(eliminated_now)})"
        if eliminated_now else
        f"{state['round']}라운드가 시작되었습니다."
    )
    log_event("INFO", room_id=room_id, action="EVENT_NEXT_ROUND", details=f"round={state['round']}")
    return jsonify({
        "success": True,
        "waiting": False,
        "boss_battle": False,
        "state": get_public_state(state, player_id)
    })

POS_ORDER = ["탱커", "딜러", "서포터", "힐러"]


def round2(v):
    # JS의 Math.round(v*100)/100 과 동일하게 반올림(0.5는 올림)
    return math.floor(v * 100 + 0.5) / 100


def apply_armor(p, dmg):
    # 갑옷 배율만큼 받는 피해를 나눠서 감소 (예: ×1.1 착용 시 피해/1.1)
    return dmg / p.get("def_mult", 1.0)


def get_party_by_position(boss_state):
    alive = [
        p for p in boss_state["party"]
        if p["hp"] > 0 and p["mp"] > 0
    ]

    sorted_party = []
    for pos in POS_ORDER:
        for p in alive:
            if p["pos"] == pos:
                sorted_party.append(p)

    return sorted_party


def support_action(supporter, boss_state, log):

    if supporter["hp"] <= 0 or supporter["mp"] <= 0 or supporter["stunned"]:
        return

    dice = random.randint(1, 6)
    log.append(f"{supporter['name']}이(가) 서포트 주사위: {dice}")

    buffs = boss_state["buffs"]

    if dice == 1:
        buffs["dmg_reduce"] = supporter["intel"] * 4
        log.append(f"→ 버프: 다음 보스 공격 피해 {buffs['dmg_reduce']} 감소")

    elif dice == 2:
        buffs["atk_buff"] = supporter["intel"] / 6
        log.append(f"→ 버프: 다음 턴 모든 팀원 공격력 +{buffs['atk_buff']:.2f}")

    elif dice == 3:
        buffs["no_stun"] = True
        log.append("→ 버프: 다음 보스의 상태이상 면역")

    elif dice == 4:
        for p in boss_state["party"]:
            if p["hp"] > 0 and p["mp"] > 0:
                p["mp"] += 1
        log.append("→ 모든 팀원 정신력 +1")

    elif dice == 5:
        buffs["heal_boost"] = 1 + (supporter["intel"] / 10)
        log.append(f"→ 버프: 이번 턴 힐량 {buffs['heal_boost']:.2f}배")

    elif dice == 6:
        inc = supporter["intel"] / 10
        for p in boss_state["party"]:
            if p["hp"] > 0 and p["mp"] > 0:
                p["maxHp"] = round2(p["maxHp"] + inc)
                p["atk"] = round2(p["atk"] + inc)
                p["hp"] = min(p["maxHp"], round2(p["hp"] + inc))
        log.append(
            f"→ 영구 버프: 모든 팀원 최대체력 +{inc:.2f}, "
            f"공격력 +{inc:.2f}, 즉시 힐 +{inc:.2f}"
        )


def player_attack(player, boss_state, log):

    if player["hp"] <= 0 or player["mp"] <= 0 or player["stunned"]:
        log.append(f"{player['name']} 행동 불가")
        return

    dmg = 0

    if player["pos"] in ("탱커", "서포터", "힐러"):
        dmg = player["atk"] * 0.5

    elif player["pos"] == "딜러":
        dice = random.randint(1, 6)
        if dice == 6:
            dmg = player["atk"] * (1 + player["intel"] / 24)
            log.append(f"{player['name']}이(가) 딜러 주사위 6! (지능 보정)")
        else:
            dmg = player["atk"]
            log.append(f"{player['name']}이(가) 딜러 주사위 {dice}")

    if boss_state["buffs"].get("atk_buff"):
        dmg += boss_state["buffs"]["atk_buff"]

    dmg = round2(dmg)
    boss_state["boss"]["hp"] = round2(max(0, boss_state["boss"]["hp"] - dmg))

    log.append(
        f"{player['name']}({player['pos']}) 공격: {dmg:.2f} 피해 "
        f"→ 보스 HP {boss_state['boss']['hp']:.2f}"
    )

    if player["pos"] == "서포터":
        support_action(player, boss_state, log)


def healer_action(healer, boss_state, log):

    if healer["hp"] <= 0 or healer["mp"] <= 0 or healer["stunned"]:
        log.append(f"{healer['name']} 행동 불가")
        return

    heal_amount = healer["intel"] * 0.2

    if boss_state["buffs"].get("heal_boost"):
        heal_amount *= boss_state["buffs"]["heal_boost"]

    heal_amount = round2(heal_amount)

    targets = [
        p for p in boss_state["party"]
        if p["hp"] > 0 and p["mp"] > 0
    ]

    for target in targets:
        old = target["hp"]
        target["hp"] = min(
            target["maxHp"],
            round2(target["hp"] + heal_amount)
        )
        log.append(
            f"{healer['name']} 힐: {target['name']} HP "
            f"{old:.2f} → {target['hp']:.2f} (힐량 {heal_amount:.2f})"
        )


def boss_action(boss_state, log):

    boss = boss_state["boss"]
    dice = random.randint(1, 6)
    log.append(f"보스 주사위: {dice}")

    if dice == 1:
        for p in get_party_by_position(boss_state):
            dmg = boss["atk"] * 0.5
            if p["pos"] == "탱커":
                dmg = dmg / 2
                t_dice = random.randint(1, 6)
                if t_dice == 6:
                    dmg = max(0, dmg - (p["intel"] / 2))
                    log.append(
                        f"{p['name']}이(가) 탱커 보호 주사위 6! "
                        f"추가 피해 감소 {p['intel']/2}"
                    )
            dmg = max(0, dmg - boss_state["buffs"].get("dmg_reduce", 0))
            dmg = apply_armor(p, dmg)
            dmg = round2(dmg)
            p["hp"] = round2(p["hp"] - dmg)
            log.append(f"{p['name']}이(가) 광역피해 {dmg:.2f} (HP {p['hp']:.2f})")

    elif dice == 2:
        front_party = get_party_by_position(boss_state)
        if front_party:
            front = front_party[0]
            dmg = boss["atk"]
            if front["pos"] == "탱커":
                t_dice = random.randint(1, 6)
                if t_dice == 6:
                    dmg = max(0, dmg - (front["intel"] / 2))
                dmg = dmg / 2
            dmg = max(0, dmg - boss_state["buffs"].get("dmg_reduce", 0))
            dmg = apply_armor(front, dmg)
            dmg = round2(dmg)
            front["hp"] = round2(front["hp"] - dmg)
            log.append(
                f"{front['name']}이(가) 단일공격 {dmg:.2f} 피해 "
                f"(HP {front['hp']:.2f})"
            )

    elif dice == 3:
        sorted_party = get_party_by_position(boss_state)

        for p in sorted_party:
            dmg = boss["atk"] * 0.3
            if p["pos"] == "탱커":
                dmg = dmg / 2
                t_dice = random.randint(1, 6)
                if t_dice == 6:
                    dmg = max(0, dmg - (p["intel"] / 2))
                    log.append(f"{p['name']} 탱커 주사위 6 (광역): {p['intel']/2} 감소")
            dmg = max(0, dmg - boss_state["buffs"].get("dmg_reduce", 0))
            dmg = apply_armor(p, dmg)
            dmg = round2(dmg)
            p["hp"] = round2(p["hp"] - dmg)
            log.append(f"{p['name']} 광역 {dmg:.2f} 피해 (HP {p['hp']:.2f})")

        if sorted_party:
            front2 = sorted_party[0]
            dmg2 = boss["atk"] * 0.7
            if front2["pos"] == "탱커":
                t_dice = random.randint(1, 6)
                if t_dice == 6:
                    dmg2 = max(0, dmg2 - (front2["intel"] / 2))
                    log.append(
                        f"{front2['name']} 탱커 주사위 6 (추가단일): "
                        f"{front2['intel']/2} 감소"
                    )
                dmg2 = dmg2 / 2
            dmg2 = max(0, dmg2 - boss_state["buffs"].get("dmg_reduce", 0))
            dmg2 = apply_armor(front2, dmg2)
            dmg2 = round2(dmg2)
            front2["hp"] = round2(front2["hp"] - dmg2)
            log.append(
                f"{front2['name']} 추가 단일 {dmg2:.2f} 피해 "
                f"(HP {front2['hp']:.2f})"
            )

    elif dice == 4:
        if boss_state["buffs"].get("no_stun"):
            log.append("버프로 상태이상 무효화")
        else:
            back_party = get_party_by_position(boss_state)
            if back_party:
                back = back_party[-1]
                back["stunned"] = True
                log.append(f"{back['name']}이(가) 상태이상에 걸려 다음턴 행동 불가")

    elif dice == 5:
        if boss["summons"] >= 2:
            log.append("이미 친구 2명 존재, 소환 실패")
        else:
            boss["summons"] += 1
            log.append(
                f"보스 친구 소환! 현재 {boss['summons']}명 "
                "(다음턴부터 공격 시작, 친구 피해: 보스ATK*0.5)"
            )

    elif dice == 6:
        for p in get_party_by_position(boss_state):
            p["mp"] = max(0, p["mp"] - 1)
            log.append(f"{p['name']} 정신력 -1 (현재 {p['mp']})")


def friends_attack(boss_state, log):

    alive = [
        p for p in boss_state["party"]
        if p["hp"] > 0 and p["mp"] > 0
    ]

    for _ in range(boss_state["boss"]["summons"]):
        if not alive:
            break
        target = random.choice(alive)
        dmg = apply_armor(target, boss_state["boss"]["atk"] * 0.5)
        dmg = round2(dmg)
        target["hp"] = round2(target["hp"] - dmg)
        log.append(f"보스 친구가 {target['name']}에게 {dmg:.2f} 피해 (HP {target['hp']:.2f})")


def is_party_dead(boss_state):
    return all(
        p["hp"] <= 0 or p["mp"] <= 0
        for p in boss_state["party"]
    )


def do_boss_turn(state):

    boss_state = {
        "boss": state["boss"],
        "party": state["boss_party"],
        "buffs": state.get("boss_buffs", {})
    }

    log = state["boss_log"]

    log.append(f"\n=== 턴 {state['boss_turn']} 시작 ===")

    boss_state["buffs"] = {}

    sorted_party = []
    for pos in POS_ORDER:
        for p in boss_state["party"]:
            if p["pos"] == pos:
                sorted_party.append(p)

    for p in sorted_party:

        if boss_state["boss"]["hp"] <= 0:
            break

        if p["hp"] <= 0 or p["mp"] <= 0:
            continue

        if p["stunned"]:
            log.append(f"{p['name']}은(는) 기절로 이번 턴 행동불가")
            p["stunned"] = False
            continue

        if p["pos"] == "힐러":
            healer_action(p, boss_state, log)

        player_attack(p, boss_state, log)

    state["boss_buffs"] = boss_state["buffs"]

    if boss_state["boss"]["hp"] <= 0:
        log.append("보스 HP 0 이하 — 승리!")
        return "win"

    boss_action(boss_state, log)

    if boss_state["boss"]["summons"] > 0:
        friends_attack(boss_state, log)

    if is_party_dead(boss_state):
        log.append("모든 팀원 사망 또는 정신력 0 — 패배")
        return "lose"

    boss_state["boss"]["hp"] = round2(boss_state["boss"]["hp"])
    for p in boss_state["party"]:
        p["hp"] = round2(p["hp"])
        p["atk"] = round2(p["atk"])
        p["maxHp"] = round2(p["maxHp"])

    state["boss_turn"] += 1

    return "continue"


# 보스전 시작
@app.route("/api/game/boss/start", methods=["POST"])
def start_boss_battle():

    data = request.get_json()
    room_id = data.get("room_id")

    state, error = get_state_or_404(room_id)
    if error:
        return error

    if not state["game_over"]:
        return jsonify({
            "success": False,
            "message": "아직 보스전을 시작할 수 없습니다."
        }), 400

    if state.get("boss_active"):
        return jsonify({
            "success": True,
            "state": get_public_state(state, data.get("player_id"))
        })

    boss_party = []
    for player in state["players"]:
        if not player["connected"] or player.get("eliminated", False):
            continue
        atk_mult = get_equipment_multiplier(player, "무기")
        int_mult = get_equipment_multiplier(player, "반지")
        def_mult = get_equipment_multiplier(player, "갑옷")

        boss_party.append({
            "player_id": player["id"],
            "name": player["name"],
            "pos": player.get("job") or "탱커",
            "maxHp": player["stats"]["hp"],
            "hp": player["stats"]["hp"],
            "atk": round2(player["stats"]["attack"] * atk_mult),
            "intel": round2(player["stats"]["intelligence"] * int_mult),
            "mp": player["stats"]["mental"],
            "def_mult": def_mult,
            "stunned": False,
            "initialMaxHp": player["stats"]["hp"],
            "initialMaxMp": player["stats"]["mental"]
        })

    if not boss_party:
        state["boss"] = {"hp": 0, "atk": 0, "summons": 0}
        state["boss_party"] = []
        state["boss_turn"] = 1
        state["boss_active"] = True
        state["boss_result"] = "lose"
        state["boss_log"] = ["모든 플레이어가 레벨 미달로 탈락하여 보스전에 참여할 인원이 없습니다."]
        state["message"] = "모든 플레이어가 레벨 미달로 탈락하여 보스전에서 패배했습니다."
        return jsonify({
            "success": True,
            "state": get_public_state(state, data.get("player_id"))
        })

    boss_hp = 52
    boss_atk = 10

    state["boss"] = {
        "hp": boss_hp,
        "atk": boss_atk,
        "summons": 0
    }
    state["boss_party"] = boss_party
    state["boss_turn"] = 1
    state["boss_buffs"] = {}
    state["boss_active"] = True
    state["boss_result"] = None
    state["boss_log"] = [
        f"전투 시작 — 보스 HP {boss_hp:.2f}, ATK {boss_atk:.2f} "
        f"/ 파티 인원 {len(boss_party)}"
    ]

    return jsonify({
        "success": True,
        "state": get_public_state(state, data.get("player_id"))
    })


# 보스전 한 턴 진행
@app.route("/api/game/boss/turn", methods=["POST"])
def advance_boss_turn():

    data = request.get_json()
    room_id = data.get("room_id")

    state, error = get_state_or_404(room_id)
    if error:
        return error

    if not state.get("boss_active"):
        return jsonify({
            "success": False,
            "message": "보스전이 시작되지 않았습니다."
        }), 400

    if state.get("boss_result"):
        return jsonify({
            "success": True,
            "state": get_public_state(state, data.get("player_id"))
        })

    result = do_boss_turn(state)

    if result != "continue":
        state["boss_result"] = result

    return jsonify({
        "success": True,
        "result": result,
        "state": get_public_state(state, data.get("player_id"))
    })
@app.errorhandler(Exception)
def handle_unexpected_error(e):
    room_id = "UNKNOWN"
    try:
        if request.is_json and request.get_json():
            room_id = request.get_json().get("room_id", "UNKNOWN")
    except Exception:
        pass

    log_event("ERROR", room_id=room_id, action=request.endpoint or "UNKNOWN_ENDPOINT", error=str(e))
    return jsonify({"success": False, "message": "서버 내부 오류가 발생했습니다."}), 500

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )