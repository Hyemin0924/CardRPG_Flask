# 협동카드 RPG — 게임 규칙 / 사용자 흐름 명세서

> 목적: 이 문서만 보고 **다른 프로그래밍 언어 / 다른 프레임워크로 재구현**할 수 있도록
> 상태 구조, 상수, 카드 효과, API 계약, 알고리즘, 라운드/턴 진행, 보스전 전투 로직,
> 그리고 포팅 시 실수하기 쉬운 부분을 모두 정리한다.
> 기준 구현: Python 3 / Flask (`app.py`) + 바닐라 JS 폴링 클라이언트 (`static/game.js`).

---

## 0. 한눈에 보는 구조

- **서버 권위 방식(server-authoritative).** 모든 규칙 판정은 서버가 한다. 클라이언트는
  화면 표시와 입력 전달만 한다.
- **방(room) 단위.** 서버 한 개가 여러 방을 동시에 관리한다. 방은 6자리 코드로 식별한다.
- **상태 저장은 인메모리 딕셔너리** `games: { room_id -> game_state }`. DB 없음. 서버 재시작 시 전부 소멸.
- **실시간 동기화 없음(웹소켓 없음).** 클라이언트가 **1초 간격 폴링**으로 상태를 새로 받는다.
- 게임은 두 단계로 나뉜다.
  1. **성장 단계**: 최대 3라운드. 카드로 스탯을 키우고 경험치로 레벨을 올린다.
  2. **보스전 단계**: 성장 결과(스탯·장비·직업)를 전투 유닛으로 환산해 자동 전투를 턴 단위로 진행한다.

---

## 1. 상수

| 이름 | 값 | 의미 |
|---|---|---|
| `MAX_ROUNDS` | `3` | 성장 단계 최대 라운드 수 |
| `MIN_CARDS_PER_TURN` | `2` | 일반 상황에서 턴 종료에 필요한 최소 카드 사용 수 |
| `MAX_CARDS_PER_TURN` | `3` | 한 턴에 사용 가능한 최대 카드 수 |
| `JOBS` | `["탱커", "딜러", "서포터", "힐러"]` | 보스전 포지션(직업) |
| 방 코드 | `[A-Z0-9]` 6자리 | 대문자 + 숫자, 서버 내 유일 |
| 시작 손패 | `5`장 | 방 생성 시 각 플레이어에게 분배 |
| 손패 목표치 | `5`장 | 라운드 전환 시 이 수치까지 보충(`refill_hands`) |
| 보스 HP | `52` | 보스전 시작 시 |
| 보스 ATK | `10` | 보스전 시작 시 |
| 보스 친구(소환) 최대 | `2` | |

### 경험치 요구치 (레벨업에 필요한 경험치, `max_players` 기준)

| 인원 | 요구 경험치 |
|---|---|
| 2 | 5 |
| 3 | 3 |
| 4 | 2 |
| 그 외(1 등) | 5 |

---

## 2. 데이터 모델

숫자 타입 표기: `int`(정수), `float`(실수). 스탯은 **상한 없음**, `부상`/`인내심 폭발`로 **음수도 가능**.

### 2.1 게임 상태 `game_state`

```
game_state {
    started:      bool          // 방 생성 시 true
    max_players:  int           // 1..4
    round:        int           // 현재 라운드 (1부터)
    max_rounds:   int           // = MAX_ROUNDS (3)
    deck:         Card[]         // 남은 덱 (뽑을 때 끝에서 pop)
    players:      Player[]       // 길이 = max_players, 인덱스 순서 고정
    message:      string         // 최근 이벤트 안내 문구 (표시용, 로직 아님)
    game_over:    bool           // "성장 3라운드가 끝나 보스전 진입 가능" 상태 (보스전 진행 중에도 true)

    split:          bool         // 이번 턴 전체 협력카드 금지 (활성값)
    split_pending:  bool         // '분열' 카드로 예약된 값 → 다음 턴 사이클에 split로 승격

    // --- 보스전 진입 후에만 존재 ---
    boss_active:  bool           // 보스전 시작됨
    boss:        { hp: float, atk: float, summons: int }
    boss_party:  BossMember[]
    boss_turn:   int             // 1부터
    boss_buffs:  Buffs           // 매 보스 턴 시작 시 {}로 초기화됨
    boss_log:    string[]        // 전투 로그 (표시용)
    boss_result: "win" | "lose" | null   // null = 전투 진행 중
}
```

### 2.2 플레이어 `Player`

```
Player {
    id:            int           // 1-based, players 배열 순서와 동일
    name:          string        // "플레이어 {id}"
    connected:     bool          // 슬롯에 실제 사람이 들어왔는지
    level:         int           // 시작 1
    experience:    int           // 시작 0
    eliminated:    bool          // 레벨 미달로 탈락 (되돌릴 수 없음)
    job:           string | null // 탱커/딜러/서포터/힐러. 방장은 생성 시, 나머지는 참가 시 확정

    stats: {
        hp:           int   // 시작 1  (보스전에서 maxHp/hp로 환산됨. "현재 체력" 아님)
        attack:       int   // 시작 1
        intelligence: int   // 시작 1
        mental:       int   // 시작 1  (보스전 mp로 환산)
    }

    hand:      Card[]        // 손패
    equipment: Card[]        // 장착 장비 (슬롯당 최고 등급 1개만 유지)

    used_cards_this_turn: int   // 이번 턴 사용한 카드 수 (0..3)
    turn_ended:           bool  // 이번 턴 종료 선언 여부

    // 상태이상: *_pending = 카드로 예약된 값, 접미사 없는 값 = 이번 턴에 실제 적용되는 값
    jealousy:         bool   // 이번 턴 자신에게 협력카드 불가
    jealousy_pending: bool   // '질투' 카드로 예약
    greed_next_turn:  bool   // 이번 턴 동료에게 협력카드 불가
    greed_pending:    bool   // '욕심' 카드로 예약
    sick:             bool   // 이번 턴 경험치 획득 불가
    sick_pending:     bool   // '질병' 카드로 예약
}
```

### 2.3 카드 `Card`

```
Card {
    name:  string
    type:  "성장" | "장비" | "협력" | "딜레마"
    text:  string     // 사람이 읽는 설명 (로직 아님)
    count: int         // 덱에 들어가는 매수 (덱 구성에만 사용)
}
```

덱에 넣을 때는 카드 정의를 **얕은 복사**해서 `count`장 만든다. `text`/`count`는 인스턴스에도
남지만 게임 로직은 `name`, `type`만 참조한다.

### 2.4 보스전 유닛 `BossMember`

```
BossMember {
    player_id:    int
    name:         string
    pos:          string        // job (없으면 "탱커")
    maxHp:        float          // = stats.hp
    hp:           float          // = stats.hp (시작 시)
    atk:          float          // = round2(stats.attack * 무기배율)
    intel:        float          // = round2(stats.intelligence * 반지배율)
    mp:           int            // = stats.mental
    def_mult:     float          // 갑옷배율 (받는 피해 나눗값). 없으면 1.0
    stunned:      bool           // 다음 자기 행동 1회 스킵
    initialMaxHp: float          // = stats.hp (표시용)
    initialMaxMp: int            // = stats.mental (표시용, MP 바 계산)
}
```

### 2.5 보스전 버프 `Buffs` (매 보스 턴 시작 시 `{}`로 초기화)

```
Buffs {
    dmg_reduce:  float   // 다음 보스 공격 1회에서 피해 정액 감소
    atk_buff:    float   // 이번 턴, 서포터 행동 "이후" 공격하는 팀원 공격력 +
    no_stun:     bool    // 이번 턴 보스의 상태이상(기절) 무효
    heal_boost:  float   // 이번 턴 힐량 배수 (예: 1.3배)
    // (서포터 주사위 4/6 효과는 버프가 아니라 파티에 즉시/영구 적용)
}
```

---

## 3. 카드 카탈로그 (전체 40장)

`대상`: `self`=자신 전용, `other`=타인 전용, `any`=자신/타인 아무나, `없음`=대상 선택 없음.

### 3.1 성장 (`type = "성장"`) — 대상 없음, `/api/game/card/use` 경로

| 이름 | 매수 | 효과 |
|---|---|---|
| 덤벨 | 2 | `attack += 2` |
| 검술훈련 | 2 | 주사위 `d6`: `1..3 → attack += 1`, `4..6 → attack += 2` |
| 책읽기 | 2 | `intelligence += 2` |
| 마법연구 | 2 | 주사위 `d6`: `1..3 → intelligence += 1`, `4..6 → intelligence += 2` |
| 수영 | 2 | `hp += 3` |
| 등산 | 2 | `hp += 2` |

### 3.2 장비 (`type = "장비"`) — 대상 없음, `/api/game/card/use` 경로

즉시 스탯 변화 없음. **보스전 시작 시**에만 배율로 반영된다.

| 이름 | 매수 | 슬롯 | 등급(tier) | 배율(mult) |
|---|---|---|---|---|
| 검 | 1 | 무기 | 1 | 1.10 |
| 가죽 갑옷 | 1 | 갑옷 | 1 | 1.05 |
| 철 갑옷 | 1 | 갑옷 | 2 | 1.10 |
| 금 갑옷 | 1 | 갑옷 | 3 | 1.15 |
| 다이아 갑옷 | 1 | 갑옷 | 4 | 1.20 |
| 은반지 | 1 | 반지 | 1 | 1.05 |
| 금반지 | 1 | 반지 | 2 | 1.10 |

**장착 규칙** (`apply_card_effect`의 장비 분기):
1. 같은 슬롯에 장착된 장비가 없으면 그냥 장착.
2. 이미 장착된 장비의 `tier >= 새 카드 tier` 이면 → 새 카드는 **버려짐(효과 없음)**.
3. 새 카드 `tier`가 더 높으면 → 기존 장비 제거하고 새 장비 장착.
- 즉 **슬롯당 최고 등급 1개만** 남는다. 무기 슬롯 카드는 `검` 하나뿐.

배율 적용(보스전 시작):
- 무기 배율 → `atk = round2(attack * mult)`
- 반지 배율 → `intel = round2(intelligence * mult)`
- 갑옷 배율 → `def_mult = mult` (받는 피해를 `dmg / def_mult`로 나눔)
- 해당 슬롯 장비 없으면 배율 `1.0`.

### 3.3 협력 (`type = "협력"`) — 대상 `any`, `/api/game/card/target`(또는 `/cooperation`) 경로

각 3매. **자신에게 쓸 때와 동료에게 쓸 때 효과가 다르다.**

| 이름 | 매수 | 자신에게 | 동료에게 |
|---|---|---|---|
| 전우의 격려 | 3 | `hp += 4` | 대상 `경험치 += 1` |
| 마법 조언 | 3 | `intelligence += 4` | 대상 `경험치 += 1` |
| 훈련 지원 | 3 | `attack += 4` | 대상 `경험치 += 1` |
| 칭찬 | 3 | `mental += 1` | 대상 `경험치 += 1` |

- 동료에게 사용 시, **대상이 `sick`(질병) 상태면 경험치 획득 없음**(카드는 소모됨).
- 경험치 획득 시 즉시 레벨업 판정(§5).
- 협력카드 사용 제약: `split`(분열), `jealousy`(질투), `greed_next_turn`(욕심) — §7.3.

### 3.4 딜레마 (`type = "딜레마"`)

| 이름 | 매수 | 대상 | 효과 | 경로 |
|---|---|---|---|---|
| 게으름 | 2 | **self 전용** | 대상 손패에서 `딜레마`가 아닌 카드 1장 랜덤 제거 + 대상이 덱에서 1장 보충. 제거 가능한 손패가 없으면 → 장착 장비 1개 랜덤 제거. 그것도 없으면 → 효과 없이 소멸 | target |
| 민폐 | 1 | **other 전용** | 대상의 (손패 + 장착 장비)를 합쳐 1개 랜덤 제거. 손패면 대상이 1장 보충 | target |
| 부상 | 1 | `any` | 스탯 후보 `[hp, attack, intelligence]` 중 1개 랜덤. 자신 대상이면 `-4`, 타인 대상이면 `-3` | target |
| 인내심 폭발 | 1 | `any` | 자신 대상: `mental -= 1`. 타인 대상: `[hp, attack, intelligence, mental]` 중 1개 랜덤 `-1` | target |
| 질병 | 1 | 없음(self 예약) | `sick_pending = true` → 다음 턴 경험치 획득 불가 | use |
| 질투 | 1 | 없음(self 예약) | `jealousy_pending = true` → 다음 턴 자신에게 협력카드 불가 | use |
| 욕심 | 1 | 없음(self 예약) | `greed_pending = true` → 다음 턴 동료에게 협력카드 불가 | use |
| 분열 | 1 | 없음(전체 예약) | `state.split_pending = true` → 다음 턴 모든 플레이어 협력카드 불가 | use |

덱 총합: 성장 12 + 장비 7 + 협력 12 + 딜레마 9 = **40장**.

### 3.5 클라이언트의 카드 라우팅 규칙 (`game.js`의 `useCard`)

- `type == "협력"` → 대상 선택 모달 → `/api/game/card/target`
- `type == "딜레마"` 이고 이름이 `{게으름, 민폐, 부상, 인내심 폭발}` 중 하나 → 대상 선택 모달 → `/api/game/card/target`
- 그 외 전부 → `/api/game/card/use`

> 서버측 `TARGETED_CARDS = ["전우의 격려","마법 조언","훈련 지원","칭찬","게으름","민폐","부상","인내심 폭발"]`
> (참고용 목록; 실제 분기는 위 라우팅과 각 핸들러의 `allowed_types`로 처리)

---

## 4. 사용자 흐름 (클라이언트)

### 4.1 화면 상태

1. **랜딩** (`#createArea`)
   - 방 만들기: 인원 수(1~4, 기본 2) + 직업 선택 → `createGame()`
   - 게임 참가: 방 코드(6자) + 직업 선택 → `joinGame()`
2. **게임 화면** (`#gameInfo`)
   - 상단바: YOU(내 id), ROOM(방 코드), ROUND(`round/max_rounds`), DECK(남은 장수), 안내 메시지
   - 좌측: 다른 플레이어들(파티) — 이름, 레벨, 스탯 4종, 손패 수, 사용 수(`n/3`), TURN ENDED 뱃지
   - 중앙: 내 플레이어 — 이름/레벨/경험치 바, 스탯 4종, 장비 칩, `이번 턴 카드 사용 n/3`, 손패(버튼)
   - 하단: `END TURN` 버튼 (`turn_ended`면 비활성)
3. **보스전 준비** (`#bossArea`) — `game_over && !boss_active`일 때 표시. `보스전 시작` 버튼
4. **보스전 화면** (`#bossBattleArea`) — `boss_active`일 때. 보스 HP/ATK/소환/턴, 파티원 HP·MP 바, 로그, `다음 턴 진행` 버튼, 승패 배너
5. **대상 선택 모달** (`#cooperationModal`) — 협력/일부 딜레마 카드 사용 시. `connected`인 모든 플레이어(자신 포함) 버튼 나열

### 4.2 전체 흐름

```
[랜딩]
  createGame(): POST /api/game/create → { room_id, player_id=1, state }
  joinGame():   POST /api/game/join   → { player_id, state }
  → roomId, myPlayerId 저장
  → 화면 전환(createArea 숨김, gameInfo 표시)
  → startPolling(): setInterval(loadGameState, 1000)

[폴링 루프] (1초마다)
  GET /api/game/state?room_id=&player_id= → state 갱신 → 화면 다시 그림
  (성공 실패와 무관하게 계속. success=false면 조용히 무시)

[내 턴 행동]
  손패 카드 클릭:
    협력            → 대상 모달 → 대상 클릭 → POST /api/game/card/target
    딜레마(대상형)  → 대상 모달 → 대상 클릭 → POST /api/game/card/target
    그 외           → POST /api/game/card/use
  END TURN 클릭    → POST /api/game/turn/end

[턴 종료 판정] (서버)
  조건 충족 못 하면 400 + 안내 → alert
  성공 시:
    아직 안 끝낸 플레이어 있음 → waiting:true (계속 폴링하며 대기)
    전원 종료 → 다음 턴 사이클 / 다음 라운드 / 보스전 진입 중 하나

[보스전]
  game_over && !boss_active → #bossArea 표시 → "보스전 시작" → POST /api/game/boss/start
  boss_active → #bossBattleArea 표시 → "다음 턴 진행" 반복 → POST /api/game/boss/turn
  boss_result 설정되면 → "다음 턴 진행" 비활성 + 승/패 배너
```

> 클라이언트는 폴링만 하므로, 다른 플레이어의 행동 결과는 **최대 1초 지연** 후 반영된다.
> 응답으로 받은 `state`로 즉시 갱신도 하고, 폴링으로도 갱신한다(경합해도 최신값으로 덮어씀).

---

## 5. 경험치 / 레벨업

```
function required_exp(state):        // 레벨 1당 필요 경험치
    switch state.max_players:
        case 2: return 5
        case 3: return 3
        case 4: return 2
        default: return 5

function add_experience(state, player, amount) -> bool leveled_up:
    player.experience += amount
    req = required_exp(state)
    leveled_up = false
    while player.experience >= req:
        player.experience -= req
        player.level += 1
        leveled_up = true
    return leveled_up
```

- 경험치를 얻는 **유일한 경로**: 동료에게 협력카드 사용(대상 `경험치 += 1`). 대상이 `sick`면 없음.
- `while` 루프이므로 한 번에 여러 레벨 상승 가능(요구치가 낮을 때).

---

## 6. 덱 / 손패

```
function create_deck():
    deck = []
    for card_def in CARD_DATA:
        repeat card_def.count times: deck.append(shallow_copy(card_def))
    shuffle(deck)                 // 균등 셔플
    return deck

function draw_card(state) -> Card | null:
    if state.deck is empty: return null
    return state.deck.pop()       // 리스트 끝에서 제거

function refill_hands(state, hand_size = 5):
    for player in state.players:
        if not player.connected or player.eliminated: continue
        while len(player.hand) < hand_size and state.deck not empty:
            player.hand.append(draw_card(state))
```

**보충 시점 차이 (중요):**
- 카드 1장 사용(`/card/use`, `/card/target`) → 사용자는 덱이 남아 있으면 **1장만** 보충. 5장으로 리필하지 않는다.
- `게으름`/`민폐`로 카드를 잃은 **대상**도 덱이 남아 있으면 1장 보충.
- **라운드 전환(다음 라운드 시작) 시에만** 모든 활성 플레이어를 `refill_hands`로 5장까지 채움.
- 덱이 비면 이후로는 손패가 점점 줄어든다.

---

## 7. 성장 단계 — 턴 & 라운드 진행

### 7.1 턴 모델

- **동시 턴제.** "턴"은 개별 플레이어가 아니라 파티 전체가 공유한다.
- 각 플레이어는 자기 페이스로 카드를 쓰고 `END TURN`을 누른다.
- **연결된 활성 플레이어 전원**이 `turn_ended`가 되어야 다음 턴 사이클로 넘어간다.
- `get_active_players(state)` = `connected == true` 이고 `eliminated == false` 인 플레이어.
  (아직 참가 안 한 슬롯은 `connected=false`라 판정에서 빠진다 → 접속자만으로 진행됨)

### 7.2 다음 턴 사이클 시작 (`start_new_turn_cycle`)

```
for p in state.players:
    p.turn_ended = false
    p.used_cards_this_turn = 0
    // 예약(pending) → 활성 승격, 직전 턴의 활성값은 그냥 덮어써서 소멸
    p.jealousy       = p.jealousy_pending;   p.jealousy_pending = false
    p.sick           = p.sick_pending;       p.sick_pending = false
    p.greed_next_turn= p.greed_pending;      p.greed_pending = false
state.split         = state.split_pending;   state.split_pending = false
```

- 상태이상은 **정확히 한 턴 사이클** 지속된다(승격된 턴 동안만).
- `질투/욕심/질병/분열`을 이번 턴에 사용하면 `*_pending`이 켜지고, **다음 턴 사이클**에 활성화된다.
  같은 턴에는 효과가 없다.

### 7.3 카드 사용 검증 — 대상형 경로 `_resolve_target_card_use` (순서 중요)

`/api/game/card/target`, `/api/game/card/cooperation` 둘 다 이 함수를 쓰며 `allowed_types = ["협력","딜레마"]`.

```
1. sender, target 조회. 하나라도 없으면 → 400 "플레이어 대상 정보가 올바르지 않습니다."
   (/card/target 경로는 그 전에: sender.eliminated → 400)
2. sender.turn_ended → 400 "이미 턴을 종료했습니다."
3. sender.used_cards_this_turn >= 3 → 400 "한 턴에 최대 3장..."
4. card_index 범위 밖 → 400 "잘못된 카드 선택입니다."
5. card = sender.hand[card_index]; is_coop = (card.type == "협력")
6. card.type 이 allowed_types 에 없으면 → 400 "이 카드는 이 방식으로 사용할 수 없습니다."
7. if is_coop:
     state.split                                    → 400 (분열)
     sender.id == target.id and sender.jealousy     → 400 (질투: 자신에게 불가)
     sender.id != target.id and sender.greed_next_turn → 400 (욕심: 동료에게 불가)
8. if card.name == "민폐":
     sender.id == target.id → 400 "자신에게 사용할 수 없습니다."
     target 의 (hand + equipment) 가 비어 있으면:
         sender 를 제외한 다른 connected 플레이어 중 (hand 또는 equipment) 보유자가 있으면
             → 400 "이 대상에겐 제거 가능한 카드/장비가 없습니다. 다른 플레이어를 선택하세요."
         아무도 없으면 → 통과 (카드 소모되며 효과 없이 소멸)
9. if card.name == "게으름":
     sender.id != target.id → 400 "게으름 카드는 자신에게만 사용할 수 있습니다."
10. ── 여기서 처음으로 카드를 손패에서 pop ── (검증 실패 시 카드는 사라지지 않음)
11. if is_coop:
      if sender == target: apply_self_cooperation_effect(target, name)
      else:
        if target.sick: (경험치 없음)
        else: add_experience(state, target, 1)
    else:
      apply_target_card_effect(state, sender, target, card)
12. sender.used_cards_this_turn += 1
13. 덱이 남아 있으면 sender.hand.append(draw_card(state))
14. state.message = <결과 문구>
```

### 7.4 카드 사용 검증 — 비대상 경로 `/api/game/card/use`

```
1. player 조회 실패 → 404
2. player.eliminated → 400
3. player.turn_ended → 400
4. player.used_cards_this_turn >= 3 → 400
5. card_index 범위 밖 → 400
6. card = player.hand.pop(card_index)
7. message = apply_card_effect(state, player, card)
8. player.used_cards_this_turn += 1
9. 덱이 남아 있으면 player.hand.append(draw_card(state))
```

> 이 경로는 `split/jealousy/greed`, `MIN_CARDS` 등을 검사하지 않는다. 성장/장비/자기예약 딜레마
> (질병·질투·욕심·분열)만 이 경로로 들어오도록 클라이언트가 라우팅한다. 서버는 타입을 강제하지 않는다.

### 7.5 효과 적용 함수

**`apply_card_effect(state, player, card)`** — 비대상 카드
```
덤벨:      attack += 2
검술훈련:  d = d6; attack += (d <= 3 ? 1 : 2)
책읽기:    intelligence += 2
마법연구:  d = d6; intelligence += (d <= 3 ? 1 : 2)
수영:      hp += 3
등산:      hp += 2
type == "장비": §3.2 장착 규칙
질투:  player.jealousy_pending = true
욕심:  player.greed_pending   = true
분열:  state.split_pending    = true
질병:  player.sick_pending    = true
그 외: 변화 없음
```

**`apply_self_cooperation_effect(player, name)`** — 협력카드를 자신에게
```
전우의 격려: hp += 4
마법 조언:   intelligence += 4
훈련 지원:   attack += 4
칭찬:        mental += 1
```

**`apply_target_card_effect(state, sender, target, card)`** — 비협력 대상형 딜레마
```
게으름:
    removable = [c for c in target.hand if c.type != "딜레마"]
    if removable:  1장 랜덤 제거; 덱 남으면 target 이 1장 보충
    elif target.equipment: 장비 1개 랜덤 제거
    else: 효과 없이 소멸
민폐:
    items = target.hand(전부) + target.equipment(전부)
    if items 비었으면: 효과 없이 소멸
    else: 1개 랜덤 제거; 손패였으면 덱 남을 때 target 이 1장 보충
부상:
    stat = random_choice([hp, attack, intelligence])
    dmg  = (sender.id == target.id) ? 4 : 3
    target.stats[stat] -= dmg
인내심 폭발:
    if sender.id == target.id:
        target.stats.mental -= 1
    else:
        stat = random_choice([hp, attack, intelligence, mental])
        target.stats[stat] -= 1
```

### 7.6 턴 종료 `/api/game/turn/end` (핵심 로직)

```
player 조회 실패 → 404 ; player.eliminated → 400

deck_empty  = state.deck 비었는가
hand_empty  = player.hand 비었는가
active      = get_active_players(state)
someone_empty_hand = active 중 손패 0장인 사람이 있는가
someone_has_cards  = active 중 손패 1장 이상인 사람이 있는가

// 턴 종료 가능 판정
if hand_empty:
    can_end = true
elif deck_empty:
    if someone_empty_hand and someone_has_cards:
        can_end = false ; msg = "덱 소진 + 손패 떨어진 사람이 있음 → 남은 카드 다 써야 종료 가능"
    else:
        can_end = (player.used_cards_this_turn >= 1) ; else msg = "최소 1장 사용해야 합니다"
else:
    can_end = (player.used_cards_this_turn >= MIN_CARDS_PER_TURN /*2*/) ; else msg = "최소 2장 사용"

if not can_end: → 400 { message: msg }

player.turn_ended = true
all_ended = active 전원이 turn_ended

if not all_ended:
    return { success:true, waiting:true, boss_battle:false, state }

// ── 전원 턴 종료됨 ──

if state.deck 비어있지 않음:
    start_new_turn_cycle(state)
    return { waiting:false, boss_battle:false, state }   // 같은 라운드 계속

// 덱은 비었음
if active 중 손패 남은 사람 있음:
    start_new_turn_cycle(state)
    return { waiting:false, boss_battle:false, state }   // 같은 라운드에서 남은 손패 소진할 때까지 계속

// 덱도 비고 손패도 다 없음 → 라운드 종료 처리
cur = state.round
if cur >= state.max_rounds /*3*/:
    required_level = cur + 1              // = 4
    active 중 level < required_level 인 플레이어: eliminated = true
    state.game_over = true
    return { waiting:false, boss_battle:true, state }
else:
    next_round = cur + 1
    required_level = next_round           // 라운드1→2: L>=2, 라운드2→3: L>=3
    active 중 level < required_level 인 플레이어: eliminated = true
    if get_active_players(state) 가 이제 아무도 없음:
        state.game_over = true
        return { waiting:false, boss_battle:true, state }   // 막다른 상태 → 보스전(자동 패배)로
    state.round = next_round
    state.deck  = create_deck()           // 새 덱 생성 + 셔플
    start_new_turn_cycle(state)
    refill_hands(state)                   // 활성 플레이어 손패 5장까지
    return { waiting:false, boss_battle:false, state }
```

**레벨 요구치 요약**
| 시점 | 필요 레벨 | 미달 시 |
|---|---|---|
| 라운드 1 종료 → 라운드 2 | `2` | 탈락 |
| 라운드 2 종료 → 라운드 3 | `3` | 탈락 |
| 라운드 3 종료 → 보스전 진입 | `4` | 탈락(보스전 파티에서 제외) |

**라운드 종료 트리거:** 자동 라운드 종료는 오직 *(덱이 완전히 소진)* + *(모든 활성 플레이어의 손패가 0장)* +
*(활성 플레이어 전원 turn_ended)* 이 동시에 만족될 때 일어난다. 덱이 남아 있으면 라운드는 계속되고
`start_new_turn_cycle`만 반복된다.

---

## 8. 상태 노출 (`get_public_state(state, my_player_id)`)

서버는 요청자 기준으로 **자기 손패만** 공개하고 남의 손패는 장수만 준다.

```
플레이어별:
    id, name, connected, level, eliminated, job, stats, equipment, experience,
    used_cards_this_turn, turn_ended,
    jealousy, jealousy_pending, greed_next_turn, greed_pending, sick, sick_pending
    if id == my_player_id: hand: Card[]      // 전체 공개
    else:                  hand_count: int   // 장수만

전역:
    started, max_players, round, max_rounds,
    deck_count (= len(deck)),
    players[], message, game_over,
    split, split_pending,
    boss_active, boss, boss_turn, boss_log, boss_party, boss_result,
    game_finished (= boss_result != null)
```

- `game_over`: "성장 단계가 끝나 보스전 진입 가능" (보스전 **진행 중에도 true**).
- `game_finished`: 보스전 승패가 확정됐는가 (`boss_result != null`).

---

## 9. HTTP API 계약

모든 응답은 JSON. 공통 실패 형태: `{ "success": false, "message": string }` + HTTP 4xx/5xx.
예상 못한 예외는 전역 핸들러가 `500 { success:false, message:"서버 내부 오류가 발생했습니다." }`.

### 9.1 `POST /api/game/create`
요청: `{ "player_count": 1..4, "job": "탱커"|"딜러"|"서포터"|"힐러" }`
- `job`이 `JOBS`에 없으면 → `"탱커"`로 강제.
- `player_count`가 없거나 `<1` 또는 `>4` → `400 "플레이어 수는 1~4명이어야 합니다."`
처리:
- `room_id` 생성(유일), 새 `game_state` 생성 및 등록.
- `started=true, max_players=player_count, round=1, deck=create_deck(), game_over=false`.
- `player_count`개의 `Player` 생성(id 1..N). `i==0`(방장)만 `job=creator_job`, 나머지 `job=null`.
- 각 플레이어에게 덱에서 5장 분배.
- `players[0].connected = true` (방장은 접속 상태).
응답: `{ "success": true, "room_id": string, "player_id": 1, "state": <public_state(1)> }`

### 9.2 `POST /api/game/join`
요청: `{ "room_id": string, "job": string }`
- `job`이 `JOBS`에 없음 → `400`.
- 방 없음 → `404 "존재하지 않는 방입니다."`
- `state.started == false` → `400 "아직 생성된 게임이 없습니다."`
- 이미 **접속한** 플레이어가 그 `job`을 가지고 있음 → `400 "'{job}' 직업은 이미 다른 플레이어가 선택했습니다."`
- `connected == false`인 첫 슬롯을 찾아 `connected=true, job=job` 설정.
- 빈 슬롯 없음 → `400 "모든 플레이어가 이미 참가했습니다."`
응답: `{ "success": true, "player_id": int, "state": <public_state(player_id)> }`

### 9.3 `GET /api/game/state?room_id=<>&player_id=<int>`
- 방 없음 → `404`.
응답: `{ "success": true, "state": <public_state(player_id)> }`

### 9.4 `POST /api/game/card/use`
요청: `{ "room_id", "player_id", "card_index" }` — §7.4 로직.
응답: `{ "success": true, "state": <public_state(player_id)> }`

### 9.5 `POST /api/game/card/target` 그리고 `POST /api/game/card/cooperation`
요청: `{ "room_id", "sender_id", "target_id", "card_index" }` — §7.3 로직. `allowed_types=["협력","딜레마"]`.
- `/card/target`은 추가로 맨 앞에서 `sender.eliminated → 400`.
응답: `{ "success": true, "state": <public_state(sender_id)> }`

### 9.6 `POST /api/game/turn/end`
요청: `{ "room_id", "player_id" }` — §7.6 로직.
응답: `{ "success": true, "waiting": bool, "boss_battle": bool, "state": <public_state(player_id)> }`
- `waiting=true`: 아직 다른 플레이어 대기 중.
- `boss_battle=true`: 성장 단계 종료, 보스전 진입 가능(`game_over=true`).

### 9.7 `POST /api/game/boss/start`
요청: `{ "room_id", "player_id"? }`
- `state.game_over == false` → `400 "아직 보스전을 시작할 수 없습니다."`
- `state.boss_active == true` → 그대로 현재 state 반환(멱등).
- `boss_party` 구성: `connected && !eliminated` 인 플레이어마다 `BossMember` 생성(§2.4, 배율 §3.2).
- `boss_party`가 비어 있으면(전원 탈락): `boss={hp:0,atk:0,summons:0}`, `boss_result="lose"`, 로그/메시지 설정 후 반환.
- 정상: `boss={hp:52,atk:10,summons:0}`, `boss_turn=1`, `boss_buffs={}`, `boss_active=true`, `boss_result=null`, `boss_log=[전투 시작 문구]`.
응답: `{ "success": true, "state": <public_state> }`

### 9.8 `POST /api/game/boss/turn`
요청: `{ "room_id", "player_id"? }`
- `state.boss_active == false` → `400 "보스전이 시작되지 않았습니다."`
- `state.boss_result` 이미 설정됨 → 그대로 반환.
- `result = do_boss_turn(state)` (§10). `result != "continue"` 이면 `state.boss_result = result`.
응답: `{ "success": true, "result": "win"|"lose"|"continue", "state": <public_state> }`

---

## 10. 보스전 전투 알고리즘

### 10.1 반올림 `round2`

```
round2(v) = floor(v * 100 + 0.5) / 100
```
- JS의 `Math.round(v*100)/100`과 동일(소수 둘째 자리, 0.5는 올림).
- **모든 언어에서 이 정의를 그대로 구현할 것.** 언어 기본 반올림(은행가 반올림 등)과 다르다.
- 부동소수 오차를 기준 구현과 맞추려면 IEEE-754 double를 쓰고 연산 순서를 동일하게 유지한다.

### 10.2 포지션 정렬

```
POS_ORDER = ["탱커", "딜러", "서포터", "힐러"]

get_party_by_position(bs):        // "살아있는" 팀원을 포지션 순으로
    alive = [p for p in bs.party if p.hp > 0 and p.mp > 0]
    result = []
    for pos in POS_ORDER:
        for p in alive:
            if p.pos == pos: result.append(p)
    return result
```
- 같은 포지션이 여러 명이면 `party` 원래 순서(=플레이어 id 순) 유지.
- "앞줄" = `result[0]` (탱커에 가까움), "뒷줄" = `result[-1]` (힐러에 가까움).

### 10.3 한 턴 진행 `do_boss_turn(state)` → `"win" | "lose" | "continue"`

```
bs = { boss: state.boss, party: state.boss_party, buffs: {} }   // ★ buffs 즉시 초기화
log.append("=== 턴 {state.boss_turn} 시작 ===")

// (A) 파티 행동 단계 — 전체 party를 POS_ORDER로 정렬 (죽은 유닛 포함해 순회하되 개별 체크)
sorted = []
for pos in POS_ORDER:
    for p in bs.party:
        if p.pos == pos: sorted.append(p)

for p in sorted:
    if bs.boss.hp <= 0: break
    if p.hp <= 0 or p.mp <= 0: continue
    if p.stunned:
        log("{p.name} 기절로 이번 턴 행동불가"); p.stunned = false; continue
    if p.pos == "힐러": healer_action(p, bs, log)
    player_attack(p, bs, log)

state.boss_buffs = bs.buffs        // 저장하지만 다음 턴 시작 때 어차피 {}로 리셋됨

if bs.boss.hp <= 0:
    log("보스 HP 0 이하 — 승리!"); return "win"

// (B) 보스 행동 단계
boss_action(bs, log)

// (C) 소환된 친구 공격
if bs.boss.summons > 0: friends_attack(bs, log)

// (D) 패배 판정
if is_party_dead(bs):
    log("모든 팀원 사망 또는 정신력 0 — 패배"); return "lose"

// (E) 정리
bs.boss.hp = round2(bs.boss.hp)
for p in bs.party: p.hp = round2(p.hp); p.atk = round2(p.atk); p.maxHp = round2(p.maxHp)
state.boss_turn += 1
return "continue"
```

**버프 타이밍(중요):** 로그 문구는 "다음 턴/다음 보스"라고 쓰지만, 실제로 `buffs`는 매 턴 시작 시
비워지고 그 턴 안에서만 유효하다. 파티 행동 순서가 `탱커→딜러→서포터→힐러`이므로:
- 서포터가 세팅한 `atk_buff`는 **그 턴에 서포터 이후 공격하는 팀원(=힐러)** 에게만 적용.
- `heal_boost`는 힐러가 서포터 뒤에 행동하므로 **그 턴** 힐에 적용.
- `dmg_reduce`, `no_stun`은 **그 턴 (B) 보스 행동**에 적용.
- 다음 턴으로는 넘어가지 않는다.

### 10.4 `player_attack(p, bs, log)`

```
if p.hp <= 0 or p.mp <= 0 or p.stunned: log("{p.name} 행동 불가"); return

if p.pos in ("탱커", "서포터", "힐러"):
    dmg = p.atk * 0.5
elif p.pos == "딜러":
    d = d6
    if d == 6: dmg = p.atk * (1 + p.intel / 24)      // 지능 보정 크리
    else:      dmg = p.atk

if bs.buffs.atk_buff exists: dmg += bs.buffs.atk_buff

dmg = round2(dmg)
bs.boss.hp = round2(max(0, bs.boss.hp - dmg))

if p.pos == "서포터": support_action(p, bs, log)     // 서포터는 공격 후 버프 발동
```

### 10.5 `healer_action(healer, bs, log)` (힐러 자기 행동 순번에서, `player_attack` 직전)

```
if healer.hp <= 0 or healer.mp <= 0 or healer.stunned: log("행동 불가"); return

heal = healer.intel * 0.2
if bs.buffs.heal_boost exists: heal *= bs.buffs.heal_boost
heal = round2(heal)

targets = [p for p in bs.party if p.hp > 0 and p.mp > 0]
for t in targets:
    t.hp = min(t.maxHp, round2(t.hp + heal))          // 전체 파티 힐, 오버힐 없음
```

### 10.6 `support_action(sup, bs, log)` (서포터가 `player_attack` 끝에 호출)

```
if sup.hp <= 0 or sup.mp <= 0 or sup.stunned: return
d = d6
switch d:
  1: bs.buffs.dmg_reduce = sup.intel * 4        // 다음 보스 공격 1회 피해 정액 감소
  2: bs.buffs.atk_buff   = sup.intel / 6        // 이후 공격 팀원 공격력 +
  3: bs.buffs.no_stun    = true                 // 이번 턴 보스 기절 무효
  4: for p in bs.party: if p.hp > 0 and p.mp > 0: p.mp += 1     // 전체 정신력 +1
  5: bs.buffs.heal_boost = 1 + sup.intel / 10   // 이번 턴 힐량 배수
  6: inc = sup.intel / 10                        // 영구 버프
     for p in bs.party: if p.hp > 0 and p.mp > 0:
         p.maxHp = round2(p.maxHp + inc)
         p.atk   = round2(p.atk + inc)
         p.hp    = min(p.maxHp, round2(p.hp + inc))
```

### 10.7 `boss_action(bs, log)`

```
boss = bs.boss ; d = d6 ; log("보스 주사위: {d}")

d == 1  (광역):
    for p in get_party_by_position(bs):
        dmg = boss.atk * 0.5
        if p.pos == "탱커":
            dmg = dmg / 2
            if d6 == 6: dmg = max(0, dmg - p.intel / 2)     // 탱커 보호 주사위
        dmg = max(0, dmg - (bs.buffs.dmg_reduce or 0))
        dmg = dmg / p.def_mult                              // apply_armor
        dmg = round2(dmg)
        p.hp = round2(p.hp - dmg)

d == 2  (앞줄 단일):
    fp = get_party_by_position(bs)
    if fp not empty:
        front = fp[0]
        dmg = boss.atk
        if front.pos == "탱커":
            if d6 == 6: dmg = max(0, dmg - front.intel / 2)   // ★ 감산 먼저
            dmg = dmg / 2                                      // ★ 그 다음 절반
        dmg = max(0, dmg - (bs.buffs.dmg_reduce or 0))
        dmg = dmg / front.def_mult
        dmg = round2(dmg)
        front.hp = round2(front.hp - dmg)

d == 3  (광역 + 앞줄 추가 단일):
    sp = get_party_by_position(bs)
    // 광역
    for p in sp:
        dmg = boss.atk * 0.3
        if p.pos == "탱커":
            dmg = dmg / 2
            if d6 == 6: dmg = max(0, dmg - p.intel / 2)
        dmg = max(0, dmg - (bs.buffs.dmg_reduce or 0))
        dmg = dmg / p.def_mult ; dmg = round2(dmg)
        p.hp = round2(p.hp - dmg)
    // 앞줄 추가 단일
    if sp not empty:
        f2 = sp[0]
        dmg2 = boss.atk * 0.7
        if f2.pos == "탱커":
            if d6 == 6: dmg2 = max(0, dmg2 - f2.intel / 2)     // ★ 감산 먼저
            dmg2 = dmg2 / 2                                     // ★ 그 다음 절반
        dmg2 = max(0, dmg2 - (bs.buffs.dmg_reduce or 0))
        dmg2 = dmg2 / f2.def_mult ; dmg2 = round2(dmg2)
        f2.hp = round2(f2.hp - dmg2)

d == 4  (상태이상):
    if bs.buffs.no_stun: log("버프로 상태이상 무효화")
    else:
        bp = get_party_by_position(bs)
        if bp not empty: bp[-1].stunned = true       // 뒷줄(힐러 쪽) 1명 기절

d == 5  (친구 소환):
    if boss.summons >= 2: log("이미 친구 2명, 소환 실패")
    else: boss.summons += 1

d == 6  (정신력 감소):
    for p in get_party_by_position(bs): p.mp = max(0, p.mp - 1)
```

> **탱커 감산/절반 순서가 d1과 d2·d3에서 다르다.** d1(광역): `/2` 후 `d6==6이면 - intel/2`.
> d2·d3 단일: `d6==6이면 - intel/2` 후 `/2`. 기준 구현 그대로 유지할 것.
> `dmg_reduce`, `no_stun`은 `d6` 굴림 없이 그냥 그 턴 값 사용(있으면).

### 10.8 `friends_attack(bs, log)`

```
alive = [p for p in bs.party if p.hp > 0 and p.mp > 0]     // ★ 한 번만 계산, 중간 갱신 안 함
repeat bs.boss.summons times:
    if alive empty: break
    target = random_choice(alive)
    dmg = round2( (bs.boss.atk * 0.5) / target.def_mult )
    target.hp = round2(target.hp - dmg)
```

### 10.9 `is_party_dead(bs)`

```
return all( p.hp <= 0 or p.mp <= 0  for p in bs.party )
```

### 10.10 승패 규칙 요약

- **승리(`win`)**: 파티 행동 단계 (A) 이후 `boss.hp <= 0`. (보스 행동 전에 즉시 판정)
- **패배(`lose`)**: 보스 행동 (B) + 친구 공격 (C) 이후 `is_party_dead`.
- 그 외에는 `continue`, `boss_turn += 1`.
- 보스전 파티가 비어 시작된 경우(전원 탈락) `boss/start`에서 즉시 `boss_result="lose"`.

---

## 11. 난수(RNG) 사용 목록

포팅 시 **결정론적 재현이 필요하면** 시드 가능한 균등 난수를 쓰고 아래 호출 순서를 지켜라.
`d6` = `1..6` 균등 정수.

| 위치 | 난수 |
|---|---|
| 방 코드 생성 | `[A-Z0-9]`에서 6회 균등 추출 |
| 덱 생성 | 40장 균등 셔플 (`random.shuffle`) |
| 검술훈련 / 마법연구 | `d6` 1회 |
| 게으름 | 제거할 손패/장비 `random.choice` |
| 민폐 | 제거할 항목 `random.choice` |
| 부상 | 스탯 `random.choice([hp, attack, intelligence])` |
| 인내심 폭발(타인) | 스탯 `random.choice([hp, attack, intelligence, mental])` |
| 보스전 딜러 공격 | `d6` 1회 |
| 서포터 행동 | `d6` 1회 |
| 보스 행동 | `d6` 1회 (+ 탱커 보호: 대상 탱커마다 `d6` 추가) |
| 친구 공격 | 대상 `random_choice(alive)`, 소환 수만큼 반복 |

---

## 12. 포팅 시 주의점 (버그 아님, 사양임)

1. **`round2`는 커스텀**: `floor(v*100 + 0.5)/100`. 언어 기본 반올림으로 대체하지 말 것.
2. **부동소수 일치**: 스탯/피해 계산은 double. 연산 순서(감산→나눗셈→round2 등)를 코드 그대로 유지해야 기준 구현과 수치가 맞는다.
3. **상태이상 pending/active 2단계**: 카드 사용 턴에는 `*_pending`만 켜지고, `start_new_turn_cycle`에서 활성값으로 승격, 딱 한 턴 뒤 자동 소멸. 같은 턴에 효과 없음.
4. **`start_new_turn_cycle`은 `state.players` 전체를 순회**(connected/eliminated 무관). 접속 안 한 슬롯도 필드가 초기화된다. 단, 턴 종료 판정은 `get_active_players`(connected && !eliminated)만 본다.
5. **레벨 요구치 비대칭**: 라운드 R→R+1 (R<3)은 `level >= R+1`, 라운드 3 종료 후 보스전 진입은 `level >= 4`.
6. **라운드는 덱이 다 떨어지고 전원 손패가 0이 될 때까지 끝나지 않는다.** 덱이 남아 있으면 `start_new_turn_cycle`만 반복.
7. **카드 사용 시 손패 보충은 1장뿐**(사용자·피해 대상 각각). 5장 리필은 라운드 전환 시에만.
8. **`게으름`은 self 전용, `민폐`는 other 전용.** `민폐` 대상이 빈손이어도 다른 접속자가 빈손이면 통과(카드 소멸).
9. **검증 실패 시 카드는 손패에서 사라지지 않는다.** `_resolve_target_card_use`는 모든 검증 후에만 `pop`.
10. **`/api/game/card/use` 경로는 split/jealousy/greed/MIN_CARDS를 검사하지 않는다.** 타입 강제도 안 함. 라우팅은 클라이언트 책임.
11. **보스전 버프는 "그 턴"만.** 로그 문구("다음 턴")를 믿지 말고 코드대로: 매 `do_boss_turn` 시작 시 `buffs = {}`.
12. **파티 행동 순서 = `탱커→딜러→서포터→힐러`**, 힐러는 자기 순번에 `healer_action` 후 `player_attack`. 서포터는 `player_attack` 끝에서 `support_action`.
13. **탱커 피해 감산/절반 순서가 보스 주사위 1번과 2·3번에서 다르다**(§10.7).
14. **`friends_attack`의 `alive` 목록은 시작 시 한 번만 계산**. 첫 타격으로 죽어도 두 번째 타격 대상 후보에 남는다.
15. **보스전은 클라이언트가 `다음 턴 진행`을 눌러야 1턴씩 전개**된다(자동 루프 없음). 서버는 요청당 딱 1턴.
16. **인메모리 상태**: 서버 재시작 = 전 게임 소멸. 영속화가 필요하면 `games` 딕셔너리를 저장소로 교체.
17. **동시성**: 기준 구현은 잠금이 없다. 멀티스레드/비동기로 포팅하면 방 단위 락이 필요.
18. **`boss.html` / `templates/boss.html`은 독립 시뮬레이터**(서버와 무관, 파라미터 수동 입력용 참고 구현). 본 게임 흐름에는 쓰이지 않는다.
19. **`/api/game/card/cooperation`와 `/api/game/card/target`는 사실상 동일**(둘 다 `_resolve_target_card_use`, `allowed_types=["협력","딜레마"]`). 클라이언트는 `/target`만 호출.
20. **주사위 크리(딜러 d6==6)**: `atk * (1 + intel/24)`. **탱커 보호(d6==6)**: `- intel/2`. **서포터 6**: 영구 스탯 상승 `intel/10`.

---

## 13. 최소 재구현 체크리스트

- [ ] 상수(§1), 카드 40장 정의(§3), 경험치 요구표(§1)
- [ ] `create_deck` / `draw_card`(끝에서 pop) / `refill_hands`
- [ ] 상태/플레이어/카드/보스 유닛 모델(§2)
- [ ] 5개 API: create, join, state, card/use, card/target(+cooperation alias)
- [ ] `_resolve_target_card_use` 검증 순서(§7.3)
- [ ] `apply_card_effect` / `apply_self_cooperation_effect` / `apply_target_card_effect`(§7.5)
- [ ] `add_experience` while-루프 레벨업(§5)
- [ ] `turn/end` 판정 트리(§7.6) + 탈락 처리 + 라운드 전환
- [ ] `start_new_turn_cycle` pending→active 승격(§7.2)
- [ ] `get_public_state` 손패 마스킹(§8)
- [ ] `round2` 커스텀 반올림(§10.1)
- [ ] `get_party_by_position` (alive + POS_ORDER)(§10.2)
- [ ] `boss/start` 파티 환산 + 장비 배율(§9.7, §3.2)
- [ ] `do_boss_turn` 단계 A~E(§10.3), player_attack / healer_action / support_action / boss_action / friends_attack / is_party_dead
- [ ] `boss/turn` = 1턴 실행 + `boss_result` 확정
- [ ] 클라이언트: 1초 폴링, 카드 라우팅(§3.5), 화면 전환(§4)
