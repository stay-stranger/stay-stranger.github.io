# stt 모듈 — 모듈 구조 패턴 체득

> 어드바이저의 가장 작은 업무 모듈로 "모듈 하나를 읽는 법"을 익힌다
> 작성 2026-10-12 · 기준 커밋 `f06317ca47` · 로컬 DB 실측
> 선행: 학습 가이드 0단계 (core · auth · permission)

---

## 0. 이 단계의 목표

STT 전문가가 되려는 게 아니다. 아무 모듈이나 열었을 때 어디부터 볼지 망설이지 않게 하려는 것이다. 엔티티를 보고, DB 를 보고, 컨트롤러를 보고, 서비스 메서드 하나를 끝까지 따라가는 그 순서가 몸에 붙는 것. stt 는 그 연습용 표본이다. 여기서 익힌 순서로 2단계 `evaluation` 의 282개 파일을 연다.

### 7월 가이드 뒤에 바뀐 것

7월 학습 가이드는 stt 를 "28개 파일"이라고 썼다. 지금은 65개다. 두 달 반 사이 커밋 21개가 들어왔고 하위 패키지가 일곱에서 열둘로 늘었다.

| 항목 | 7월 27일 | 지금 |
|---|---|---|
| Java 파일 | 28 | 65 |
| 하위 패키지 | 7 | 12 (`lineage` · `policy` · `enums` · `logging` · `util` 추가) |
| `STTController` | — | 1,285줄 |
| `STTService` | — | 2,077줄 |

늘어난 37개는 대부분 두 가지 새 관심사다. `lineage/` 열두 개는 한 통화가 어느 길로 들어왔는지(실시간인지, 녹취 동기화인지, 가져오기인지)를 기록하는 계보이고, `policy/` 열네 개는 발화를 외부 AI 로 보내도 되는지 공공과 민간을 가려 판정하는 정책 엔진이다. 둘 다 1단계에서는 건너뛴다. 핵심 흐름은 7월과 같고 읽을 파일 여섯도 그대로 있다.

---

## 1. 이 모듈이 하는 일 (한 문장)

교환기와 AI 소프트폰과 배치 수집기가 보내는 통화 시작·종료 이벤트와 발화 문장을 받아, 저장하고, 실시간 화면으로 뿌리고, 통화가 끝나면 다른 모듈에 "끝났다"고 알린다.

```
 외부 STT 엔진 ──POST /api/stt/event (S/E)──▶ ┐
                                              │  ① 필터 (노이즈·중복 차단)
 외부 STT 엔진 ──POST /api/stt/message ──────▶ ┤  ② DB 저장  stt_events / stt_messages
                                              │  ③ 실시간 전송  WebSocket /topic/stt/...  (또는 Kafka)
                                              └  ④ END 이면 SttCallCompletedEvent 발행
                                                        │
                                                        ▼
                                   assist(상담보조 세션 종료) · orchestration(워크플로우 트리거)
                                   addressbot · simulation  ← 다른 모듈이 구독
```

분석도 평가도 요약도 여기서는 하지 않는다. 강어귀는 물을 받아 두고 물길을 정할 뿐이고, 그 물에 무엇이 섞였는지 재는 일은 아래 물길의 몫이다. `sttanalytics`(3단계)와 `evaluation`(2단계)과 `assist` 가 이 모듈이 띄운 이벤트를 받아서 그 일을 한다.

---

## 2. 읽는 순서 (6개 파일, 이 순서대로)

| # | 파일 | 줄 수 | 읽는 법 |
|---|---|---|---|
| 1 | `entity/STTEvent.java` | 88 | 전부. 컬럼 일곱 개만 보면 된다 |
| 2 | `entity/STTMessage.java` | 202 | 컬럼 부분만. 메서드 둘은 4절에서 |
| 3 | DB SELECT | — | 5절 쿼리 실행. 건너뛰지 않는다 |
| 4 | `controller/STTController.java` | 1,285 | 78~190줄 `receiveSTTMessage` 만. 나머지는 목록만 훑는다 |
| 5 | `service/STTService.java` | 2,077 | 173~349줄 `saveSTTMessage` 만 |
| 6 | `ingest/SttIngestFilter.java` | 183 | 전부. 짧고 주석이 좋다 |

4번과 5번이 천 줄을 넘는다고 겁먹을 필요는 없다. 각각 메서드 하나만 끝까지 따라가면 된다. 학습 가이드 2절의 "관심 있는 메서드 하나만 끝까지 추적"이 이 얘기다.

---

## 3. entity — 이 도메인의 "명사" 2개

### 3.1 `STTEvent` → 테이블 `stt_events` — 통화의 시작과 끝

통화 한 건은 행 두 개로 남는다. `S` 한 줄, `E` 한 줄. 로컬 DB 에서 최근 통화 다섯 건을 열어 보니 전부 `S,E` 쌍이었다.

| 컬럼 | 의미 | 실데이터 예 |
|---|---|---|
| `call_id` | 통화 식별자. 외부가 정한다 | `CALL20260805143000_50000141` |
| `extension_number` | 상담사 내선(DN) | `50000141` |
| `user_id` | 상담사 ID | `import`, `batch`, `agent01` |
| `call_time` | 시작/종료 시각 | `2026-08-05 14:30:00` |
| `type` | `S`=시작 / `E`=종료 | |
| `created_at` | 우리 서버가 받은 시각 | |

나머지 컬럼 `source_event_id`, `source_system`, `source_sequence`, 그리고 `*_claimed_at` 과 `*_published_at` 은 2026-10-03 에 들어온 재전송 멱등성(STT-010) 장치다. 같은 이벤트가 두 번 와도 두 번 처리하지 않기 위한 것인데, 로컬 데이터는 전부 NULL 이다. 레거시 경로로 들어온 데이터라 그렇다. 1단계에서는 "그런 칸이 있다"까지만 알고 지나간다.

### 3.2 `STTMessage` → 테이블 `stt_messages` — 발화 문장 하나

발화 한 문장이 행 하나다. 로컬 DB 에 2,774행, 통화 107건이 있으니 통화당 스물여섯 문장쯤 된다.

| 컬럼 | 의미 | 주의 |
|---|---|---|
| `call_id` | 어느 통화의 문장인가 | `stt_events.call_id` 와 논리 연결 (FK 없음) |
| `call_type` | 화자. `TX`=상담사 / `RX`=고객 | 아래 함정 |
| `channel_type` | `@Deprecated` — 읽지 말 것 | 아래 함정 |
| `extension_number` / `user_id` | 이벤트와 동일 | |
| `start_time` / `end_time` | 발화 시각 | DTO 는 epoch ms 로 받아 변환 |
| `offset_ms` | 통화 시작 기준 몇 ms 지점인가 | Oracle 동기화 데이터만 값 있음 |
| `text` | 원문. `updatable = false` | 절대 안 바뀜 |
| `corrected_text` | AI 교정문 (없으면 NULL) | |
| `correction_status` | `UNCHECKED` / `APPLIED` / `FAILED` | |
| `customer_type` | `G`(민간) / `P`(공공) — AI 전송 차단 분기 | |
| `counsel_type_id` | 상담유형 (counseltype 모듈) | 로컬은 전부 NULL |

### 화자 판정 — `call_type` 이 정답이고 `channel_type` 은 함정이다

실데이터를 세어 보면 왜 헷갈리는지 바로 보인다.

```
call_type  channel_type  건수
TX         NULL           803   ← 정상 (상담사)
RX         NULL           788   ← 정상 (고객)
IN         MIX            520   ← 화자 미상 (옛 Oracle 동기화: IN=인바운드 방향)
TX         VOICE          171   ← 손으로 만든 JSON 가져오기
TX         TX             161   ← 옛 데이터 (channel_type 에도 화자를 넣던 시절)
```

`channel_type` 한 칸에 테넌트 ID 와 화자와 매체, 세 가지 뜻이 겹쳐 쌓여 있다. 엔티티 주석에 그 경위가 적혀 있는데, 생산자마다 이 칸에 다른 것을 넣어 보내던 세월이 그대로 지층이 됐다. 그래서 화자는 반드시 `util/SttSpeakerUtils` 를 거쳐 판정한다. `isAgent(message)` 는 `call_type` 이 `TX` 일 때만 참이고, `MIX` 나 `VOICE` 나 `IN` 처럼 화자를 모르는 값은 기존 호출부와의 호환을 위해 고객 쪽으로 떨어진다.

> 🔴 **신규 코드에서 `getCallType().equals("TX")` 를 직접 쓰지 않는다.** 화자 판정의 SSOT 는 `SttSpeakerUtils` 하나다.

### 엔티티 안의 메서드 둘 — 원문은 건드리지 않는다

`STTMessage` 에는 `initializeCorrection()` 과 `applyCorrection()` 이 있다. 규칙은 하나다. `text` 는 저장된 뒤 절대 수정하지 않는다. 교정은 `corrected_text` 에 쓰고, 이력은 `stt_message_correction_revisions` 에 덧붙이기만 한다. `correction_version` 이 하나 오르고 revision 행이 하나 늘어난다.

로컬 DB 의 revision 은 0건이다. 교정이 돈 적이 없다는 뜻이다. `corrected_text` 가 2,446건 차 있는 건 가져오기 때 원문을 그대로 복사해 넣은 것이지 교정의 결과가 아니다.

---

## 4. DB 실습 — 코드 전에 데이터부터

```bash
docker exec -it mariadb mariadb -u <계정> -p local_db
```

```sql
-- ① 통화 1건은 이벤트 몇 행인가?  → 2행 (S, E)
SELECT call_id, GROUP_CONCAT(type ORDER BY call_time) types, COUNT(*) n
FROM stt_events GROUP BY call_id ORDER BY MAX(id) DESC LIMIT 5;

-- ② 통화 1건의 대화 흐름 (화자 교대가 보인다)
SELECT call_type, start_time, LEFT(text, 50) text
FROM stt_messages
WHERE call_id = 'CALL20260805143000_50000141'
ORDER BY start_time, id;

-- ③ 화자값 분포 — 3.2 의 함정을 눈으로 확인
SELECT call_type, channel_type, COUNT(*) FROM stt_messages GROUP BY 1,2 ORDER BY 3 DESC;

-- ④ 이벤트는 있는데 발화가 없는 통화 / 그 반대 (FK 가 없어서 생길 수 있다)
SELECT (SELECT COUNT(DISTINCT call_id) FROM stt_events)   AS calls_with_events,
       (SELECT COUNT(DISTINCT call_id) FROM stt_messages) AS calls_with_messages;
-- 로컬: 86 vs 107 → 발화만 있고 이벤트 없는 통화가 21개 (가져오기 경로)
```

②를 돌리면 `TX` 의 인사, `RX` 의 용건, `TX` 의 본인 확인이 번갈아 내려온다. 이 화면을 한 번 머리에 넣고 나면 코드를 읽다가 `callType` 이 뭐였는지 다시 찾아보는 일이 없어진다.

---

## 5. controller — 밖에서 할 수 있는 "동사"

`@RequestMapping("/api/stt")` 아래 엔드포인트가 서른 개쯤 있다. 중요한 건 수신 둘이고 나머지는 관리 화면이 쓰는 조회와 수정이다.

### 5.1 수신 2개 (외부 STT 엔진이 호출)

| 메서드 | 경로 | 보안 | 역할 |
|---|---|---|---|
| POST | `/api/stt/event` | permitAll | 통화 시작/종료 |
| POST | `/api/stt/message` | permitAll | 발화 1문장 |

인증·권한 글의 자가진단 3번, "`/api/stt/message` 가 permitAll 인데 왜 안전한가"의 현장이 여기다. 외부 교환기는 JWT 를 보낼 줄 모른다. 대신 이 엔드포인트는 받은 것을 저장할 뿐 데이터를 돌려주지 않고(응답은 처리 결과 코드뿐이다), 운영에서는 망 분리와 IP 제한이 그 앞을 지킨다.

### 5.2 `receiveSTTMessage` 따라가기 (78~190줄)

이 메서드 하나에 모듈의 설계가 다 들어 있다. 순서가 곧 설계다.

```
① 빈 텍스트면 200 OK 로 조용히 무시          (연동 시스템이 빈 발화를 보낸다)
② sttIngestFilter.shouldDiscardMessage()      노이즈·중복 통화 차단 → 7절
③ persistWithSingleRetry()                    DB 저장. 실패 시 1회 재시도, 그래도 실패면 503
      └ 저장 실패하면 ④⑤ 를 하지 않는다  ← "화면엔 보이는데 DB 엔 없는 발화" 방지
④ 재전송(duplicateSourceEvent)이면 여기서 끝   실시간 전송 반복 안 함
⑤ broadcastRealtimeFirst()                    WebSocket 로 화면에 먼저 뿌리고
   forbiddenWordScanProcessor.scanIfAgent()    상담사(TX) 발화만 금지어 검사
   routeMessage()                              Redis fan-out · 웹훅 · 어시스트 이벤트
⑥ finally: recordMessageLineage()             계보 기록. 실패해도 예외 안 던짐
⑦ 처리 시간이 임계 넘으면 WARN 로그            filterMs / saveMs / scanRouteMs 분리 측정
```

읽으면서 세 가지를 확인한다. 왜 저장이 실시간 전송보다 먼저인가. 주석은 "원문 저장 성공 후에만 실시간/후속 라우팅으로 전파한다"고 답한다. 화면에는 떴는데 DB 에는 없는 발화를 만들지 않겠다는 뜻이다. 왜 계보 기록은 `finally` 안에 있고 예외를 삼키는가. 계보 기록이 고장 났다고 이미 저장된 발화의 실시간 전달까지 막으면 안 되기 때문이다(STT-017 결정). 그리고 2026-09-23 자 주석. 누군가 이 수신 경로에서 LLM 교정 호출을 떼어 냈다. 결과가 로그에만 남는 호출이었는데 HTTP 스레드에서 LLM 을 동기로 기다리는 구조였다. 수신 경로는 LLM 을 기다리지 않는다는 것이 이 모듈의 원칙으로 남았다.

### 5.3 `receiveSTTEvent` (190~325줄) — 훑기만

구조는 message 와 같다. 필터, 저장, 라우팅, 계보. 다른 점은 하나다.

> 🔑 **END(`E`) 저장이 끝나면 `SttCallCompletedEvent` 를 발행한다.** 이것이 다른 모듈로 나가는 유일한 출구다. 8절에서 누가 받는지 본다.

키 있는 수신(STT-010)의 선점·503·재전송 분기가 메서드의 절반을 차지하는데, 1단계에서는 `sourceEventId == null` 인 레거시 분기(231~245줄)만 읽으면 된다. 로컬 데이터가 전부 그 길로 들어왔다.

### 5.4 나머지 엔드포인트 — 목록만

| 묶음 | 예 | 쓰는 화면 |
|---|---|---|
| 조회 | `GET /conversation/{callId}` · `/conversations/search` | 통화 목록 · 실시간 |
| 화자 수정 | `PATCH /conversations/{callId}/speakers` · `/restore` · `/classify` | 통화 상세 |
| 가져오기/내보내기 | `/conversations/import` · `/export-excel` | 통화 목록 |
| 삭제·복제 | `DELETE /conversations/{callId}` · `/duplicate` | 통화 목록 |
| 시뮬레이션 복사 | `/conversations/{callId}/copy-to-simulation` | 시뮬레이션 |

React 쪽 진입점은 `web-react/src/services/stt.service.ts` 이고, 그걸 쓰는 화면이 `pages/SttConversationListPage.tsx` 와 `pages/SttRealtimePage.tsx` 다. 실시간 WebSocket 은 `services/stt-realtime.service.ts` 가 맡는다.

---

## 6. service — `saveSTTMessage` 하나만 추적 (173~349줄)

```
① sourceEventId / sourceSystem 정규화         키 없으면 서버가 내부 ID 발급, system 은 'DEFAULT'
② 키가 있으면 기존 행 조회                    있으면 duplicate 표시하고 return (재전송)
③ DTO → 엔티티 복사
     time(epoch ms) → start_time(LocalDateTime)   epochMillisToLdt()
     text 그대로 / correctedText 는 initializeCorrection() 으로
     customerType 없으면 'G'
④ messageRepository.save()                    DataIntegrityViolation 이면 unique 충돌 판정 → 409 재료
⑤ eventPublisher.publishEvent(SttChunkProcessedEvent)   실시간 상담보조(assist)·proactive 가 구독
```

### 이 메서드에 `@Transactional` 이 없는 이유

169줄 주석에 날짜가 있다. 2026-05-28. 상담사 서른 명이 동시에 발화를 저장하는 상황에서 커밋이 60초 넘게 걸리고 HikariCP 커넥션이 새는 일이 있었다. 원인은 `STTMessage` 의 보조 인덱스 여러 개와 바깥 트랜잭션의 커밋 단계가 잠금을 두고 다툰 것이었고, 해결은 바깥 트랜잭션을 걷어 내고 repository 의 짧은 자체 트랜잭션에 맡기는 것이었다. 누군가 그날 애너테이션 한 줄을 뗐고 그 이유를 주석으로 남겼다.

> 🔴 **`saveSTTMessage` 에 `@Transactional` 을 다시 붙이지 않는다.** CRITICAL 7 "모든 `@Transactional` 에 timeout" 과 8 "readOnly 안에서 외부 I/O 금지" 가 겨누는 것이 바로 이런 커밋 지연이다. 규칙이 왜 있는지 궁금해지면 이 주석으로 돌아온다.

### 같은 파일의 나머지는 언제 보나

| 메서드 | 볼 때 |
|---|---|
| `saveSTTEvent` (352~) | END → `SttCallCompletedEvent` 발행 지점이 궁금할 때 |
| `importConversations` (840, `timeout = 300`) | 가져오기가 왜 느린지 볼 때 |
| `searchConversationsWithPagination` (1,345~, 오버로드 4개) | 통화 목록 검색 조건 추가할 때 |
| `updateSpeakers` / `restoreSpeakers` | 화자 수정 기능. `original_call_type` 백업 규칙 |

---

## 7. ingest — `SttIngestFilter` (183줄, 전부 읽기)

AI 소프트폰을 쓰면 같은 상담사 내선으로 STT 가 두 벌 들어온다. 한 줄기는 맑고 한 줄기는 흙탕인데, 둘 다 같은 강어귀로 흘러든다.

| 출처 | `call_id` 모양 | 품질 | 처리 |
|---|---|---|---|
| `BRIDGE` (AI 소프트폰) | 순수 UUID `c1de5af6-…` | 정제됨, 고객 발화만 | 신뢰 |
| `ACS_NATIVE` (레거시 교환기) | `<UUID>_<채널>_<DN>` | "감사합니다/요/지" 노이즈, 종료 후 유입 | Bridge 활성 DN 이면 차단 |
| `UNKNOWN` | `SIM_…`, `CALL2026…` 등 | — | 차단 안 함 |

차단 사유 다섯 가지가 메트릭 `stt.ingest.discarded{reason=…}` 로 남는다.

| reason | 조건 |
|---|---|
| `native_ai_softphone` | 같은 DN 에 Bridge 통화 활성 중 들어온 native 발화 |
| `native_carryover` | 이미 차단된 native 통화의 나머지 발화·종료 |
| `post_call_end` | END 이후 들어온 늦은 발화 |
| `filler_token` | `요,지,음,어,아,그,네에,음음` 1음절 단독 발화 |
| `echo_phrase` | 고객(RX) 채널 TTS 에코 — 기본 비활성 (정상 발화 손실 위험) |

설정은 `application.yml` 의 `stt.ai-softphone.*` 과 `stt.noise-filter.*` (206~218줄)에 있다. 읽으면서 볼 포인트는 `processEventAndShouldDiscard()` 다. native 의 END 를 차단하면 `SttCallCompletedEvent` 도 나가지 않고, 그러면 요약과 워크플로우가 돌지 않는다. "AI 소프트폰 통화인데 요약이 안 떴다"는 문의가 오면 이 메트릭부터 본다.

---

## 8. 이 모듈이 밖으로 내보내는 것 — 다음 단계로 가는 다리

stt 는 라우팅 서비스를 빼면 다른 모듈을 직접 부르지 않는다. Spring 이벤트 두 개로만 말한다.

| 이벤트 | 발행 시점 | 구독자 (다른 모듈) |
|---|---|---|
| `SttChunkProcessedEvent` | 발화 저장 직후 | `assist` 큐 워커, `workspace/proactive` (실시간 상담보조) |
| `SttCallCompletedEvent` | END 저장 직후 | `assist` (세션 종료·최종요약), `orchestration/trigger` (워크플로우), `addressbot`, `simulation` |

> ⚠️ **평가(`evaluation`)는 이 이벤트로 시작하지 않는다.** 평가 대상은 `EvaluationTargetCollectScheduler` 가 10분마다 `stt_messages` 를 긁어 모은다. 학습 가이드 7절의 "스케줄러가 여섯이다"가 이 얘기다. 2단계에서 직접 확인한다.

구독자 가운데 조건이 붙은 것이 있다. `@EventListener(condition = "!@sttAssistQueueProperties.enabled")`. `stt.assist-queue.enabled` 가 참이면 리스너 대신 영속 대기열이 처리한다(기본 거짓). 지금은 두 길이 있고 설정으로 고른다는 것까지만 기억한다.

### 실시간 전송 경로

```
MessageRoutingService.broadcastRealtimeFirst()
   ├ Kafka ON  (dev)   → kafkaTemplate.send(stt-message 토픽) → KafkaConsumerService → WebSocket
   └ Kafka OFF (local) → WebSocketMessagingService 직접
                            /topic/stt/message/{extensionNumber}
                            /topic/stt/event/{extensionNumber}
```

로컬은 Kafka 가 꺼져 있어 WebSocket 으로 바로 간다. React 실시간 화면은 자기 내선의 토픽을 구독한다.

---

## 9. 보너스 — `counseltype` (35개)

두 번째 표본이다. stt 와 크기가 비슷한데 AI 자동 분류가 붙어 있어서, 둘을 나란히 놓으면 차이가 바로 보인다. 15분이면 된다.

테이블 `counsel_type` 은 로컬에 92행이 있고 `parent_id`, `depth`, `path = STD-1 …` 로 트리를 이룬다. 일반 CRUD 위에 `reclassify`(AI 재분류 실행)와 `merge` 와 `similarity-groups`(유사 이름 묶기)가 얹혀 있고, 그래서 `service/impl/` 에 `CounselTypeRaceSafeWriter` 와 `StandardCatalogResolver` 와 `ReclassificationRunServiceImpl` 같은 실행 이력·동시성 방어가 추가로 생겼다. 인가는 클래스 레벨 `@PreAuthorize("isAuthenticated()")` 하나뿐인데, 이것이 "role 하드코딩 금지"(CRITICAL 19)의 모범 사례다.

stt 와 견주어 볼 것은 단위의 변화다. "쓰기 한 번"이 아니라 "실행 한 번"이 단위가 되는 순간 `*Run` 엔티티와 상태 컬럼이 생긴다. 2단계의 `evaluation_execution` 이 똑같은 모양으로 기다리고 있다.

---

## 10. 함정 모음

| # | 함정 | 대응 |
|---|---|---|
| 1 | `channel_type` 으로 화자 판정 | 금지. `SttSpeakerUtils.isAgent()` 만 사용 |
| 2 | `stt_events` ↔ `stt_messages` FK 없음 | 발화만 있는 통화·이벤트만 있는 통화가 둘 다 존재한다. JOIN 시 LEFT 로 |
| 3 | `text` 는 `updatable = false` | 원문 수정 요구는 `corrected_text` + revision 으로 |
| 4 | 수신 경로에서 LLM·외부 호출 | 2026-09-23 제거 사례. 수신은 저장+전송만 |
| 5 | `saveSTTMessage` 에 `@Transactional` 추가 | 2026-05-28 사고 재발. 추가하지 말 것 |
| 6 | native END 차단 → 요약·워크플로우 미실행 | 메트릭 `stt.ingest.discarded` 확인 |
| 7 | 로컬 Kafka OFF / dev ON | 실시간이 안 뜨면 프로파일부터 확인 |
| 8 | `start_time` 은 epoch ms 로 받는다 | 초 단위로 보내면 1970년이 된다 (`epochMillisToLdt` 에 2000년 임계값 방어 있음) |
| 9 | 테넌트 ID 는 HTTP 헤더로 받는다 | `channel_type` 에 넣던 옛 방식과 혼동 금지 |

---

## 11. 자가진단

1. 통화 1건은 `stt_events` 에 몇 행이 생기나? 각 행의 `type` 은?
2. 발화의 화자는 어느 컬럼으로 판정하나? `IN`/`MIX` 는 무엇인가?
3. `text` 와 `corrected_text` 는 뭐가 다른가? 교정 이력은 어디에 쌓이나?
4. 발화 저장이 실패하면 실시간 화면 전송은 어떻게 되나? (5.2 ③)
5. `POST /api/stt/message` 가 permitAll 인데 왜 괜찮은가?
6. 통화가 끝났다는 사실을 `assist` 모듈은 어떻게 알게 되나?
7. AI 소프트폰 통화에서 레거시 교환기 STT 가 같이 들어오면 어느 쪽을 버리나? 근거는 `call_id` 의 어떤 특징인가?
8. 평가는 `SttCallCompletedEvent` 로 시작되나?
9. `saveSTTMessage` 에 `@Transactional` 이 없는 이유는?
10. 위 여섯 파일이 각각 어느 디렉토리에 있었는지, 안 보고 말할 수 있나?

여덟 개 이상이면 2단계로 간다. 10번이 안 되면 학습 가이드 2절의 디렉토리 구조를 한 번 더 보고 넘어간다. 그게 이 단계의 진짜 목표였다.

---

## 부록: 파일 위치 요약

| 관심사 | 파일 |
|---|---|
| 통화 이벤트 엔티티 | `stt/entity/STTEvent.java` |
| 발화 엔티티 | `stt/entity/STTMessage.java` |
| 교정 이력 엔티티 | `stt/entity/STTMessageCorrectionRevision.java` |
| 수신 API | `stt/controller/STTController.java` (`receiveSTTMessage` 78줄 · `receiveSTTEvent` 190줄) |
| 저장 | `stt/service/STTService.java` (`saveSTTMessage` 173줄 · `saveSTTEvent` 352줄) |
| 수신 필터 | `stt/ingest/SttIngestFilter.java` · `SttCallIdClassifier` · `AiSoftphoneSessionTracker` |
| 화자 판정 SSOT | `stt/util/SttSpeakerUtils.java` |
| 실시간 라우팅 | `stt/service/MessageRoutingService.java` → `WebSocketMessagingService` / `KafkaProducerService` |
| 통화 종료 이벤트 | `stt/event/SttCallCompletedEvent.java` |
| 수신 보안 규칙 | `core/config/LocalSecurityConfig.java` 174~190줄 |
| 설정 | `application.yml` 138~218줄 (`stt:` 블록) |
| React 서비스 | `web-react/src/services/stt.service.ts` · `stt-realtime.service.ts` |
| React 화면 | `web-react/src/pages/SttConversationListPage.tsx` · `SttRealtimePage.tsx` |
| 보너스 모듈 | `counseltype/` (엔티티 `CounselType` → 테이블 `counsel_type`) |

---

*문서 끝*
