let gameState = null;

let myPlayerId = null;

let pollingInterval = null;

// 서버 하나에서 여러 방(게임)을 동시에 관리하기 위한 방 코드
let roomId = null;


// 인원 수 선택 버튼(1~4) 클릭 처리
document
    .getElementById("playerCountPicker")
    .querySelectorAll("button")
    .forEach(
        button => {

            button.addEventListener(
                "click",
                () => {

                    document
                        .getElementById("playerCountPicker")
                        .querySelectorAll("button")
                        .forEach(
                            b => b.classList.remove("selected")
                        );

                    button.classList.add("selected");

                    document
                        .getElementById("playerCount")
                        .value =
                        button.dataset.count;
                }
            );
        }
    );


async function createGame() {

    const playerCount =
        parseInt(
            document
                .getElementById("playerCount")
                .value
        );

    const job =
        document
            .getElementById("createJobSelect")
            .value;

    const response =
        await fetch(
            "/api/game/create",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    player_count: playerCount,
                    job: job
                })
            }
        );

    const data =
        await response.json();

    if (!data.success) {

        alert(data.message);

        return;
    }

    roomId =
        data.room_id;

    myPlayerId =
        data.player_id;

    gameState =
        data.state;

    showRoomCode();

    showGame();

    startPolling();

    renderGame();
}


async function joinGame() {

    const inputRoomId =
        document
            .getElementById("roomIdInput")
            .value
            .trim()
            .toUpperCase();

    if (!inputRoomId) {

        alert("방 코드를 입력해주세요.");

        return;
    }

    const job =
        document
            .getElementById("joinJobSelect")
            .value;

    const response =
        await fetch(
            "/api/game/join",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    room_id: inputRoomId,
                    job: job
                })
            }
        );

    const data =
        await response.json();

    if (!data.success) {

        alert(data.message);

        return;
    }

    roomId =
        inputRoomId;

    myPlayerId =
        data.player_id;

    gameState =
        data.state;

    showRoomCode();

    showGame();

    startPolling();

    renderGame();
}


function showRoomCode() {

    // HTML에 id="roomCodeDisplay" 요소가 있으면 방 코드를 보여줍니다.
    const display =
        document
            .getElementById("roomCodeDisplay");

    if (display) {

        display.textContent =
            `${roomId} (다른 플레이어에게 알려주세요)`;
    }
}


function showGame() {

    document
        .getElementById("createArea")
        .classList
        .add("hidden");

    document
        .getElementById("gameInfo")
        .classList
        .remove("hidden");
}


function startPolling() {

    if (pollingInterval) {

        clearInterval(
            pollingInterval
        );
    }

    pollingInterval =
        setInterval(
            loadGameState,
            1000
        );
}


async function loadGameState() {

    if (!myPlayerId) {

        return;
    }

    const response =
        await fetch(
            `/api/game/state?room_id=${roomId}&player_id=${myPlayerId}`
        );

    const data =
        await response.json();

    if (!data.success) {

        return;
    }

    gameState =
        data.state;

    renderGame();
}


function renderGame() {

    renderGameInfo();

    renderParty();

    renderMyPlayer();

    checkBossBattle();
}


function renderGameInfo() {

    document
        .getElementById("myPlayerInfo")
        .textContent =
        `플레이어 ${myPlayerId}`;

    document
        .getElementById("roundInfo")
        .textContent =
        `${gameState.round} / ${gameState.max_rounds}`;

    document
        .getElementById("deckInfo")
        .textContent =
        `${gameState.deck_count}장`;

    document
        .getElementById("message")
        .textContent =
        gameState.message;
}


function renderParty() {

    const partyArea =
        document
            .getElementById("partyArea");

    partyArea.innerHTML = "";

    gameState.players
        .filter(
            player =>
                player.id !== myPlayerId
        )
        .forEach(
            player => {

                const playerDiv =
                    document
                        .createElement("div");

                playerDiv.className =
                    "party-player";

                playerDiv.innerHTML = `

                    ${
                        player.turn_ended
                            ? '<span class="turn-badge">TURN ENDED</span>'
                            : ""
                    }

                    <h3>${player.name}</h3>
                    <span class="level-tag">LV ${player.level}</span>

                    <div class="stat-row">
                        <span>공격 <b>${player.stats.attack}</b></span>
                        <span>지능 <b>${player.stats.intelligence}</b></span>
                        <span>체력 <b>${player.stats.hp}</b></span>
                        <span>정신 <b>${player.stats.mental}</b></span>
                    </div>

                    <div class="played-count">
                        <span>손패 ${player.hand_count}장</span>
                        <span>사용 ${player.used_cards_this_turn}/3</span>
                    </div>

                `;

                partyArea
                    .appendChild(
                        playerDiv
                    );
            }
        );
}


function renderMyPlayer() {

    const myPlayer =
        gameState.players
            .find(
                player =>
                    player.id === myPlayerId
            );

    if (!myPlayer) {

        return;
    }

    const requiredExp =
        getRequiredExperience();

    const expPercent =
        Math.min(
            100,
            Math.round(
                (myPlayer.experience / requiredExp) * 100
            )
        );

    const equipmentHtml =
        myPlayer.equipment.length > 0
            ? myPlayer.equipment
                .map(
                    item =>
                        `<span class="equipment-chip">${item.name}</span>`
                )
                .join("")
            : '<span class="equipment-chip">장비 없음</span>';

    const area =
        document
            .getElementById("myPlayerArea");

    area.innerHTML = `

        <div class="my-player">

            <div class="identity">

                <div class="avatar">
                    ${myPlayer.name.charAt(0)}
                </div>

                <div class="exp-track">
                    <h2>${myPlayer.name}</h2>
                    <div class="exp-label">
                        LV ${myPlayer.level} · EXP ${myPlayer.experience} / ${requiredExp}
                    </div>
                    <div class="exp-bar">
                        <div class="exp-fill" style="width:${expPercent}%"></div>
                    </div>
                </div>

                <div class="stats">
                    <div class="stat">
                        <div class="stat-label">공격</div>
                        <div class="stat-value">${myPlayer.stats.attack}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">지능</div>
                        <div class="stat-value">${myPlayer.stats.intelligence}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">정신</div>
                        <div class="stat-value">${myPlayer.stats.mental}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">체력</div>
                        <div class="stat-value">${myPlayer.stats.hp}</div>
                    </div>
                </div>

            </div>

            <div class="equipment-row">
                ${equipmentHtml}
            </div>

            <div class="turn-usage">
                이번 턴 카드 사용: ${myPlayer.used_cards_this_turn} / 3
            </div>

            <div
                id="myCards"
                class="cards"
            ></div>

        </div>

    `;

    const endTurnBtn =
        document
            .getElementById("endTurnBtn");

    if (endTurnBtn) {

        endTurnBtn.disabled =
            myPlayer.turn_ended;
    }

    const cardsArea =
        document
            .getElementById("myCards");

    myPlayer.hand
        .forEach(
            (card, index) => {

                const cardButton =
                    document
                        .createElement("button");

                cardButton.className =
                    `card type-${card.type}`;

                cardButton.innerHTML = `

                    <div class="card-name">
                        ${card.name}
                    </div>

                    <div class="card-type">
                        ${card.type}
                    </div>

                    <div class="card-text">
                        ${card.text}
                    </div>

                `;

                cardButton.onclick =
                    () => useCard(index);

                cardsArea
                    .appendChild(
                        cardButton
                    );
            }
        );
}


async function useCard(cardIndex) {

    const myPlayer =
        gameState.players.find(
            player =>
                player.id === myPlayerId
        );

    const card =
        myPlayer.hand[cardIndex];


    if (card.type === "협력") {

        openTargetModal(
            cardIndex,
            "cooperation"
        );

        return;
    }


    if (card.type === "딜레마") {

        if (
            card.name === "게으름"
            || card.name === "민폐"
            || card.name === "부상"
            || card.name === "인내심 폭발"
        ) {

            openTargetModal(
                cardIndex,
                "dilemma"
            );

            return;
        }
    }


    useNormalCard(cardIndex);
}
async function useNormalCard(cardIndex) {

    const response =
        await fetch(
            "/api/game/card/use",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({

                    room_id:
                        roomId,

                    player_id:
                        myPlayerId,

                    card_index:
                        cardIndex

                })
            }
        );

    const data =
        await response.json();

    if (!data.success) {

        alert(data.message);

        return;
    }

    gameState =
        data.state;

    renderGame();
}
let selectedCooperationCardIndex = null;
function getRequiredExperience() {

    const playerCount =
        gameState.max_players;

    if (playerCount === 2) {
        return 5;
    }

    if (playerCount === 3) {
        return 3;
    }

    if (playerCount === 4) {
        return 2;
    }

    return 5;
}

let selectedTargetCardIndex = null;

let selectedTargetCardType = null;


function openTargetModal(
    cardIndex,
    cardType
) {

    selectedTargetCardIndex =
        cardIndex;

    selectedTargetCardType =
        cardType;


    const targets =
        document
            .getElementById(
                "cooperationTargets"
            );

    targets.innerHTML = "";

    const myPlayer =
        gameState.players.find(
            player =>
                player.id === myPlayerId
        );


    const card =
        myPlayer.hand[cardIndex];
    
    document.getElementById("cooperationModalTitle").textContent =
    card.name + " 사용";


    gameState.players
        .filter(
            player =>
                player.connected
        )
        .forEach(
            player => {

                const button =
                    document
                        .createElement(
                            "button"
                        );

                button.className =
                    "target-option";


                button.textContent =
                    player.id === myPlayerId
                        ? `${player.name} (나)`
                        : player.name;


                button.onclick =
                    () => useTargetCard(
                        player.id
                    );


                targets
                    .appendChild(
                        button
                    );
            }
        );


    document
        .getElementById(
            "cooperationModal"
        )
        .classList
        .remove(
            "hidden"
        );
}


function closeCooperationModal() {

    document
        .getElementById(
            "cooperationModal"
        )
        .classList
        .add("hidden");

    selectedCooperationCardIndex =
        null;
}
async function useTargetCard(
    targetId
) {

    const response =
        await fetch(
            "/api/game/card/target",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({

                    room_id:
                        roomId,

                    sender_id:
                        myPlayerId,

                    target_id:
                        targetId,

                    card_index:
                        selectedTargetCardIndex

                })
            }
        );


    const data =
        await response.json();


    if (!data.success) {

        alert(
            data.message
        );

        return;
    }


    closeCooperationModal();


    gameState =
        data.state;


    renderGame();
}
async function endTurn() {

    const response =
        await fetch(
            "/api/game/turn/end",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({

                    room_id:
                        roomId,

                    player_id:
                        myPlayerId

                })
            }
        );

    const data =
        await response.json();

    if (!data.success) {

        alert(data.message);

        return;
    }

    gameState =
        data.state;

    renderGame();
}


function checkBossBattle() {

    const bossArea =
        document.getElementById("bossArea");

    const bossBattleArea =
        document.getElementById("bossBattleArea");

    const mainGameLayout =
        document.getElementById("mainGameLayout");

    const turnEndBarWrap =
        document.getElementById("turnEndBarWrap");

    if (gameState.boss_active) {

        bossArea.classList.add("hidden");
        bossBattleArea.classList.remove("hidden");
        mainGameLayout.classList.add("hidden");
        turnEndBarWrap.classList.add("hidden");

        renderBossBattle();

        return;
    }

    bossBattleArea.classList.add("hidden");
    mainGameLayout.classList.remove("hidden");
    turnEndBarWrap.classList.remove("hidden");

    if (gameState.game_over) {

        bossArea.classList.remove("hidden");

    } else {

        bossArea.classList.add("hidden");
    }
}


async function startBossBattle() {

    const response =
        await fetch(
            "/api/game/boss/start",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    room_id: roomId,
                    player_id: myPlayerId
                })
            }
        );

    const data =
        await response.json();

    if (!data.success) {

        alert(data.message);

        return;
    }

    gameState =
        data.state;

    renderGame();
}


async function nextBossTurn() {

    const response =
        await fetch(
            "/api/game/boss/turn",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    room_id: roomId,
                    player_id: myPlayerId
                })
            }
        );

    const data =
        await response.json();

    if (!data.success) {

        alert(data.message);

        return;
    }

    gameState =
        data.state;

    renderBossBattle();
}


function renderBossBattle() {

    const boss =
        gameState.boss;

    if (!boss) {

        return;
    }

    document.getElementById("bossHpDisplay").textContent =
        boss.hp.toFixed(2);

    document.getElementById("bossAtkDisplay").textContent =
        boss.atk.toFixed(2);

    document.getElementById("bossSummonsDisplay").textContent =
        boss.summons;

    document.getElementById("bossTurnDisplay").textContent =
        gameState.boss_turn;

    const partyArea =
        document.getElementById("bossPartyArea");

    partyArea.innerHTML = "";

    gameState.boss_party.forEach(
        member => {

            const hpRatio =
                Math.max(0, member.hp / member.maxHp) * 100;

            const mpRatio =
                Math.max(
                    0,
                    Math.min(
                        100,
                        (member.mp / (member.initialMaxMp || member.mp || 1)) * 100
                    )
                );

            const div =
                document.createElement("div");

            div.className =
                "boss-member" +
                (member.hp <= 0 || member.mp <= 0 ? " dead" : "");

            div.innerHTML = `

                <div class="row-top">
                    <strong>${member.name}</strong>
                    <span class="pos-tag">
                        [${member.pos}]
                        ${member.stunned ? "· 기절" : ""}
                    </span>
                </div>

                <div class="bar-track">
                    <div class="bar-fill hp-fill" style="width:${hpRatio}%"></div>
                </div>

                <div class="bar-track">
                    <div class="bar-fill mp-fill" style="width:${mpRatio}%"></div>
                </div>

                <div class="stat-line">
                    HP ${member.hp.toFixed(2)} / ${member.maxHp.toFixed(2)}
                    · MP ${member.mp}
                    · ATK ${member.atk.toFixed(2)}
                    · INT ${member.intel.toFixed(2)}
                </div>

            `;

            partyArea.appendChild(div);
        }
    );

    const logArea =
        document.getElementById("bossLog");

    logArea.textContent =
        gameState.boss_log.join("\n");

    logArea.scrollTop =
        logArea.scrollHeight;

    const nextTurnBtn =
        document.getElementById("bossNextTurnBtn");

    const resultBanner =
        document.getElementById("bossResultBanner");

    if (gameState.boss_result) {

        nextTurnBtn.disabled = true;

        resultBanner.classList.remove("hidden", "win", "lose");
        resultBanner.classList.add(gameState.boss_result);

        resultBanner.textContent =
            gameState.boss_result === "win"
                ? "🏆 승리! 보스를 물리쳤습니다."
                : "💀 패배... 파티가 전멸했습니다.";

    } else {

        nextTurnBtn.disabled = false;
        resultBanner.classList.add("hidden");
    }
}