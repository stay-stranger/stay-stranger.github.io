# evaluation 모듈 — 핵심 업무 도메인

> 어드바이저의 심장. 통화 한 건이 점수가 되기까지의 길을 스케줄러에서 AI 호출까지 따라간다
> 작성 2026-10-12 · 기준 커밋 `f06317ca47` · 로컬 DB 실측
> 선행: 1단계 stt 모듈 (자가진단 여덟 문항 이상)

---

## 0. 이 단계의 목표

이 모듈의 스케줄 설정 테이블을 처음 열었을 때 나는 일곱 줄의 `next_execution_at` 을 보고 있었다. 전부 과거였다. 4월, 6월, 7월, 8월. 그중 두 줄은 `is_active` 가 켜져 있었다. 서버를 띄우면 60초 안에 그 두 계획이 돈다는 뜻이다. 지금이 저녁 8시든 새벽 3시든, cron 에 뭐라고 적혀 있든 상관없이. "설정한 시간 외에 평가가 돈다"는 문의가 왜 생기는지 그 화면 하나로 알았다.

이 글의 목표는 그 한 줄을 읽을 수 있게 되는 것이다. stt 에서 익힌 손으로 282개 파일 중 일곱을 열고, 스케줄러가 깨어나는 순간부터 AI 가 문항 하나에 점수를 매기는 순간까지 메서드 하나를 끝까지 따라간다. 평가는 이 제품이 파는 것이고, 현업에서 받는 문의 대부분이 이 길 어딘가에서 생긴다.

### 7월 가이드 뒤에 바뀐 것

7월 학습 가이드는 evaluation 을 282개로 적었고 지금도 282개다. 숫자가 같아서 안 바뀐 줄 알면 틀린다. 두 달 반 사이 이 모듈을 건드린 커밋이 38개다. 파일은 275개에서 7개가 늘었을 뿐이지만 그 사이에 배치 시작 방식이 바뀌었고, 스케줄 평가 대상을 고르는 쿼리가 바뀌었고, 트랜잭션 경계가 다시 그어졌다.

| 항목 | 7월 27일 | 지금 |
|---|---|---|
| Java 파일 | 275 | 282 |
| 하위 패키지 | — | 14 (`service` 64 · `dto` 69 · `entity` 34 · `repository` 32 · `statistics` 32 · `controller` 17) |
| 엔드포인트 | — | 260 |
| `@Entity` | — | 33 |
| 스케줄 잡 (`@Scheduled`) | 6 | 6 (그대로) |

가장 큰 변화는 9월 24일에 있었다. 운영에서 5분 주기 스케줄 평가가 하루 여덟 번 "실행을 찾을 수 없습니다"로 죽었다. 트랜잭션 안에서 비동기 배치를 바로 불러서, 다른 스레드가 커밋도 안 된 실행 행을 찾으러 갔던 것이다. 경쟁이라 절반쯤만 실패했고, 같은 실수를 복제한 호출부가 다섯 곳이었다. 그날 누군가 그 다섯을 `EvaluationBatchStarter` 한 곳으로 모았다. 110줄짜리 파일이고, 6절에서 지나간다.

---

## 1. 이 모듈이 하는 일 (한 문장)

평가 계획에 따라 통화를 골라 평가 대상으로 등록하고, 때가 되면 대상을 묶어 실행을 만들고, 대상마다 평가표의 문항을 AI 에 하나씩 물어 점수를 매겨 결과로 남긴다.

```
 ① 모으기   stt_messages ──(10분 수집기 / 연동 동기화 / 수동 등록)──▶ evaluation_target   PENDING → DATA_READY
 ② 고르기   evaluation_schedule_config.next_execution_at <= now ──▶ 60초 폴링이 깨어남
 ③ 묶기     DATA_READY 대상 N건 ──▶ evaluation_execution (+ execution_target)   대상은 IN_PROGRESS 로
 ④ 매기기   대상 1건 ──▶ 대화 텍스트 ──▶ 문항마다 AI 호출 ──▶ evaluation_result (+ question_evaluation_detail)
 ⑤ 알리기   WebSocket · 알림센터 · 웹훅 · AiModuleTriggerEvent(워크플로우)
```

이 모듈은 시험장이다. 계획은 시험 일정표이고, 평가표는 시험지, 대상은 수험 명단, 실행은 회차, 결과는 성적표다. 비유는 여기까지만 쓰겠다. 테이블 이름이 이미 그 역할을 말하고 있어서 비유보다 테이블이 더 정확하다. `evaluation_plan` → `evaluation_target` → `evaluation_execution` → `evaluation_result`. 이 네 테이블의 순서가 곧 위 다섯 단계의 순서다.

---

## 2. 읽는 순서 (7개 파일, 이 순서대로)

| # | 파일 | 줄 수 | 읽는 법 |
|---|---|---|---|
| 1 | `entity/EvaluationTarget.java` | 311 | 컬럼과 enum 둘. 상태 전이는 3절 |
| 2 | `entity/EvaluationPlan.java` | 486 | 상단 컬럼 열다섯만. enum 넷의 뜻 |
| 3 | DB SELECT | — | 4절 쿼리 넷. 건너뛰지 않는다 |
| 4 | `service/impl/EvaluationSchedulerServiceImpl.java` | 985 | 444~495줄 `checkAndExecuteSchedules` 와 640~696줄 `executeScheduledDirect` 만 |
| 5 | `service/impl/EvaluationBatchStarter.java` | 110 | 전부. 머리 주석이 사고 보고서다 |
| 6 | `service/impl/EvaluationBatchProcessorImpl.java` | 1,165 | 103~283줄 `processBatchAsync` 의 while 루프만 |
| 7 | `service/EvaluationService.java` | 1,461 | 820~919줄 `executeEvaluation` 과, 거기서 부르는 셋(484 · 674 · 630줄) |

stt 는 여섯이었는데 하나가 늘었다. 5번 파일이 그것이다. 110줄밖에 안 되지만 이 모듈에서 가장 최근에 피를 본 자리라 뺄 수 없었다. 7번 파일은 천사백 줄이지만 역시 메서드 하나와 그 메서드가 부르는 셋만 보면 된다.

---

## 3. entity — 이 도메인의 "명사" 다섯

`@Entity` 가 33개다. 다 볼 필요 없다. 평가 한 건이 지나가는 길에 놓인 다섯과, 그 다섯이 끌고 다니는 자식 테이블 셋만 보면 나머지는 설정이거나 통계거나 코칭이다.

| 엔티티 | 테이블 | 한 줄 | 로컬 행 수 |
|---|---|---|---|
| `EvaluationPlan` | `evaluation_plan` | 누구를 · 언제 · 몇 건 · 어떤 평가표로 | 9 |
| `EvaluationTarget` (+`EvaluationTargetCall`) | `evaluation_target` (+`_call`) | 평가할 통화 한 건. 콜 ID 는 자식 테이블에 1:N | 20 (+20) |
| `EvaluationScheduleConfig` | `evaluation_schedule_config` | 계획 하나당 한 줄. `next_execution_at` 과 락 | 7 |
| `EvaluationExecution` (+`EvaluationExecutionTarget`) | `evaluation_execution` (+`_target`) | 한 번의 배치 실행과 그 안의 대상 목록 | 13 (+65) |
| `EvaluationResult` (+`QuestionEvaluationDetail`) | `evaluation_result` (+`question_evaluation_detail`) | 통화 한 건의 성적표와 문항별 채점 | 620 (+6,140) |

평가표는 `EvaluationForm` 과 `EvaluationQuestion` 이다. 계획이 평가표 하나를 가리키고, 평가표가 문항을 여럿 갖는다. 로컬에는 평가표 8개에 문항 131개가 있다.

### 3.1 `EvaluationTarget` — 상태가 곧 자격이다

대상에는 상태 컬럼이 둘 있다. `evaluation_status` 가 평가의 진행이고, `source` 가 어디서 들어왔는지다. 둘 다 enum 이고 파일 안에 뜻이 적혀 있다.

```
PENDING ──(STT 데이터 확인)──▶ DATA_READY ──(실행에 묶임)──▶ IN_PROGRESS ──▶ COMPLETED
   │                              │                              │
   └──(30일 미도착)──▶ EXPIRED    └──(재시도 소진)──▶ EXPIRED      ├──▶ FAILED (AI 장애)
                                                                 ├──▶ SKIPPED (대화 없음 등)
                                                                 └──(서버 죽음·60분 정체)──▶ DATA_READY 복원
```

스케줄 평가가 고르는 건 `DATA_READY` 뿐이다. `PENDING` 은 등록은 됐는데 발화가 아직 안 들어온 상태라 고르지 않고, `IN_PROGRESS` 는 이미 누가 집어 간 상태라 고르지 않는다. 이 한 줄이 "왜 내 대상이 평가되지 않나"의 답 절반이다. `PENDING` 에서 `DATA_READY` 로 올려 주는 건 `EvaluationReadinessServiceImpl` 80줄이고, 서버가 뜰 때와 녹취 동기화가 끝났다는 이벤트가 올 때 돈다. 30일이 지나도 발화가 안 오면 `EXPIRED` 로 내린다.

`source` 는 넷이다. `STT_MANUAL` 은 화면에서 통화 목록을 보고 손으로 넣은 것, `STT_AUTO` 는 10분마다 도는 수집기가 넣은 것, `ACS` 는 교환기 연동 테이블에서 동기화한 것, `EXTERNAL_SYNC` 는 외부 데이터소스 스케줄 연동이다. 앞의 둘은 같은 메서드 `doCreateFromStt` 가 만들고 source 값만 다르다. 발화가 이미 있으면 처음부터 `DATA_READY`, 없으면 `PENDING` 으로 태어난다.

### 3.2 `EvaluationPlan` — enum 넷이 다섯 가지 축 중 셋이다

계획에는 enum 이 넷 있다. `status` 는 `PENDING / ACTIVE / COMPLETED` 이고 `ACTIVE` 만 스케줄이 돈다. 나머지 셋이 헷갈리는 자리다.

| 컬럼 | 값 | 화면 표기 | 뜻 |
|---|---|---|---|
| `evaluation_mode` | `CONSULTANT` / `SCHEDULE` | 상담사 기준 / 연동 대상 기준 | 대상을 어디서 고르나 |
| `execution_mode` | `MANUAL` / `SCHEDULED` | 수동 실행 / 자동(Cron) | 누가 실행을 만드나 |
| `execution_type` | `SINGLE` / `GROUP` | 대상 단건 / 상담사 그룹 | 실행 단위 |

`SCHEDULE` 이라는 값이 "스케줄로 실행한다"는 뜻이 아니라는 게 함정이다. 그건 `execution_mode = SCHEDULED` 의 몫이다. `evaluation_mode = SCHEDULE` 은 "할당된 상담사와 무관하게 `source = EXTERNAL_SYNC` 인 대상만 고른다"는 뜻이고, 화면에서는 "연동 대상 기준"이라고 부른다. 이 값은 DB 에 박힌 enum 이라 이름을 못 바꾸고, 그래서 6월에 라벨만 통일했다. 결과 테이블에서는 같은 값이 `source_type` 이라는 다른 이름으로 복사된다.

---

## 4. DB 실습 — 코드 전에 데이터부터

```bash
docker exec -it mariadb mariadb -u <계정> -p local_db
```

```sql
-- 1) 스케줄의 시계. 이 글의 첫 문단이 본 화면
SELECT s.id, s.plan_id, p.status, p.cron_expression, s.is_active,
       s.last_executed_at, s.next_execution_at, s.lock_owner, s.lock_expire_at, NOW() AS now
FROM evaluation_schedule_config s JOIN evaluation_plan p ON p.id = s.plan_id;

-- 2) 대상의 자격. DATA_READY 가 몇 건인가
SELECT evaluation_status, source, COUNT(*) FROM evaluation_target GROUP BY 1, 2;

-- 3) 실행 한 번에 몇 건, 몇 초 걸렸나
SELECT e.id, e.execution_type, e.status, e.total_count, e.success_count, e.fail_count,
       TIMESTAMPDIFF(SECOND, e.started_at, e.completed_at) AS sec
FROM evaluation_execution e ORDER BY e.id DESC LIMIT 5;

-- 4) 성적표 한 장을 문항까지 펼친다
SELECT r.id, r.call_id, r.total_score, r.max_score, r.pass_status,
       d.question_id, d.is_correct, d.similarity_score, LEFT(d.ai_reasoning, 50) AS why
FROM evaluation_result r JOIN question_evaluation_detail d ON d.result_id = r.id
WHERE r.evaluation_target_id IS NOT NULL ORDER BY r.id DESC, d.id LIMIT 14;
```

1번에서 본 것은 이미 말했다. 활성 계획 둘(9번과 10번)의 `next_execution_at` 이 7월 29일과 8월 4일이다. 2번은 로컬에 `DATA_READY` 가 한 건도 없다고 답한다. 20건 중 19건이 `COMPLETED`, 1건이 `FAILED`, 전부 `EXTERNAL_SYNC`. 그래서 지금 로컬 서버를 띄우면 두 계획이 60초 안에 깨어나되 고를 대상이 없어 "평가할 대상이 없습니다"를 찍고 `next_execution_at` 만 다음 cron 시각으로 밀어 둔다. 이 두 쿼리를 나란히 보면 "돈다"와 "평가한다"가 다른 일이라는 걸 알게 된다.

3번은 7월 29일 저녁의 실행 네 건을 보여 준다. 계획 9번, 대상 5건씩, 162초에서 183초. 4번의 `processing_time_ms` 와 맞춰 보면 대상 하나에 34초에서 40초, 문항은 일곱이었다. 문항 하나에 5초쯤이다. 이 숫자를 머리에 넣어 두면 나중에 "평가가 느리다"는 말을 들었을 때 느린 건지 아닌지 바로 안다.

4번에는 함정이 하나 있다. `WHERE r.evaluation_target_id IS NOT NULL` 을 빼면 620건이 나오는데 그중 600건은 7월 31일 새벽 2시 35분에 한꺼번에 들어간 매트릭스 화면 검증용 데이터다. 대상도 없고 상담사도 없다. 실제 평가 길을 지나온 성적표는 20장이다.

> 💡 **cron 은 시계가 아니다.** 실행 판정은 "지금이 cron 시각인가"가 아니라 "`next_execution_at` 이 현재를 지났는가"다. cron 은 실행이 끝난 뒤 다음 `next_execution_at` 을 계산하는 데만 쓰인다. 그래서 서버가 배치 도중 죽으면 그 값이 갱신되지 않고, 재기동 뒤 시간대와 무관하게 한 번 돈다.

---

## 5. 스케줄러 — 시계가 여섯인데 cron 을 보는 건 하나

이 모듈에는 `@Scheduled` 가 여섯 있다. 계획 화면의 cron 은 그중 하나에만 영향을 주고 나머지 다섯은 24시간 자기 박자로 돈다.

| 잡 | 주기 | 위치 | cron |
|---|---|---|---|
| 스케줄 실행 폴링 `checkAndExecuteSchedules` | 60초 | `EvaluationSchedulerServiceImpl` 444줄 | 적용 |
| STT 자동 수집 | 10분 | `scheduler/EvaluationTargetCollectScheduler` 27줄 | 상시 |
| 대상 자동 동기화 폴링 | 1분 | `scheduler/EvaluationTargetSyncScheduler` 28줄 | 상시 |
| 동기화 로그 정리 | 매일 03:00 | 같은 파일 42줄 | 상시 |
| 정체 실행 정리 `cleanupStaleExecutions` | 15분 | `EvaluationSchedulerServiceImpl` 168줄 | 상시 |
| 만료 락 해제 | 5분 | 같은 파일 922줄 | 상시 |

### 5.1 `checkAndExecuteSchedules` 따라가기 (444~495줄)

여섯 중 하나를 끝까지 본다. 52줄이다.

1. `findDueSchedules(now)` (535줄). 쿼리는 `EvaluationScheduleConfigRepository` 76~83줄에 있다. 조건 다섯: 계획이 `ACTIVE`, `execution_mode = SCHEDULED`, `next_execution_at <= now`, 락이 없거나 만료됐고, 계획이 상시이거나 종료일이 오늘 이후.
2. 스케줄마다 `tryAcquireLock` (892줄). UPDATE 한 줄로 `lock_owner` 에 인스턴스 ID 를 적는다. 서버가 둘이면 한 쪽만 성공한다. 만료는 30분.
3. `isInBlockedTime`. 금지 시간대에 걸리면 건너뛰고 `next_execution_at` 만 다시 계산한다.
4. `executeScheduledDirect(planId)` (640줄). 여기서 실행이 만들어진다. 아래에서.
5. `recordScheduleSuccess` (545줄). `last_executed_at = now`, `next_execution_at = cron.next(now)`. 실패해도 `recordScheduleFailure` 가 같은 일을 한다. 안 그러면 다음 폴링에 또 돈다.
6. `finally` 에서 `releaseLock`.

5번이 4절의 노트가 말한 그 자리다. `next_execution_at` 은 `cron.next(지금)` 이지 `cron.next(직전 예정 시각)` 이 아니다. 7월 29일 실행 93번은 cron 이 `0 */5` 인데 18:45:40 에 시작했다. 폴링이 60초라 예정 시각에서 최대 59초 늦게 깨어난다. 그 정도는 정상이다.

### 5.2 `executeScheduledDirect` (640~696줄)

진행 중인 실행이 있으면 0 을 돌려주고 끝. 없으면 `transactionTemplate` 안에서 넷을 한다. `resolveScheduledTargets` (757줄) 로 대상을 고르고, `EvaluationExecution` 한 줄을 만들고, `createExecutionTargets` (704줄) 로 대상마다 `execution_target` 한 줄을 만들면서 대상의 상태를 `IN_PROGRESS` 로 바꾼다. 다음 폴링이 같은 대상을 또 집지 못하게 하는 장치다. 마지막으로 `batchStarter.startAfterCommit(executionId)`.

대상을 고르는 규칙은 `evaluation_mode` 가 정한다. `CONSULTANT` 면 `DATA_READY` 이면서 계획에 할당된 상담사의 `user_id` 이면서 계획 기간 안에 만들어진 것. `SCHEDULE` 이면 `DATA_READY` 이면서 `source = EXTERNAL_SYNC` 이면서 계획 시작일 이후. 둘 다 `evaluations_per_run` 건까지만 집는다(기본 10). 그래서 대상이 100건이고 cron 이 5분이면 열 번 돌아야 다 끝난다.

> 🔴 **`EvaluationExecutionServiceImpl.executeScheduled` 는 아무도 부르지 않는다.** 196~237줄에 스케줄 실행을 만드는 메서드가 또 있는데 호출부가 없다. 스케줄러 서비스가 `executeScheduledDirect` 라는 자기 버전을 들고 있기 때문이다. 둘이 대상 고르는 쿼리까지 다르니, 스케줄 평가 대상을 디버깅할 때 이 메서드를 열고 있으면 엉뚱한 코드를 읽는 것이다.

---

## 6. service — `executeEvaluation` 하나만 추적 (820~919줄)

실행이 만들어진 뒤 평가 한 건이 지나는 길은 파일 셋을 건넌다. 먼저 다리를 보고, 그다음 메서드 하나를 끝까지 본다.

### 6.1 다리 둘 — `EvaluationBatchStarter` 와 `processBatchAsync`

`startAfterCommit` 은 지금 트랜잭션이 커밋된 뒤에 가상 스레드 하나를 띄워 `processBatchAsync` 를 부른다. 9월 24일 전에는 호출부가 트랜잭션 안에서 `@Async` 메서드를 바로 불렀고, 배치 스레드가 커밋 전의 실행 행을 찾다가 실패했다. 머리 주석에는 그다음 발견도 적혀 있다. 커밋한 스레드에서 바로 배치를 시작하면 실행기 한도(10) 에 막혔을 때 커넥션을 쥔 채 기다리게 되어, 한 번 더 가상 스레드로 넘겼다.

`processBatchAsync` (103줄) 는 `@Transactional` 이 없다. 주석이 이유를 말한다. AI 평가 중 커넥션을 오래 쥐어 누수가 났다. 루프는 단순하다. `PENDING` 인 `execution_target` 을 20건씩 꺼내 `processTarget` (922줄) 을 부르고, 성공·실패 수를 세고, 배치 사이 500ms 를 쉰다. 연속 실패가 10건이면 멈추고, 도는 중에 계획이 비활성화되면 멈추면서 대상을 `DATA_READY` 로 돌려놓는다. `processTarget` 은 `execution_target` 을 `IN_PROGRESS` 로 바꾼 뒤 `evaluationService.executeEvaluation(planId, targetId, true)` 를 부른다. 세 번째 인자가 "상태 체크는 이미 했으니 건너뛰라"는 뜻이다.

### 6.2 `executeEvaluation` 을 다섯 단계로

```java
// service/EvaluationService.java:819
@Transactional(propagation = Propagation.NOT_SUPPORTED)   // ★ 이 메서드는 트랜잭션 밖이다
public Long executeEvaluation(Long planId, Long targetId, boolean skipStatusCheck) {
    BatchTargetInfo info = selfProvider.getObject().loadBatchTarget(targetId, skipStatusCheck); // ① REQUIRES_NEW 30s
    ...
    combinedConversationText = getConversationTextByCallIds(allCallIds);                       // ② 대화 텍스트
    ...
    consultant = consultantRepository.findByExtensionNumber(info.extensionNumber())...;         // ③ 상담사
    Long resultId = evaluateCall(consultant, representativeId, PASS_THRESHOLD, planId,
                                 combinedConversationText, targetId).join();                    // ④ 평가 (LLM)
    selfProvider.getObject().markBatchTargetStatus(targetId, resultId);                         // ⑤ REQUIRES_NEW 10s
    return resultId;
}
```

①은 `loadBatchTarget` (919줄) 이다. 짧은 트랜잭션 하나를 열어 대상과 콜 ID 목록을 읽고 바로 닫는다. 콜 ID 가 여럿이면 쉼표로 이어 대표 ID 를 만든다. ②는 `getConversationTextByCallIds` (1258줄). `sttService.getConversationFromDb` 로 발화를 모아 시간순으로 줄을 만든다. `[ID:123][고객] 안녕하세요` 꼴이다. 화자는 `callType` 이 `RX` 면 고객, 아니면 상담사. 1단계에서 본 "`call_type` 이 정답" 규칙이 여기서 AI 에게 건네는 문장의 화자 라벨이 된다. 교정문(`correctedText`)이 있으면 그것을 쓴다.

③은 상담사 찾기다. 내선번호로 찾고, 없으면 `userId` 로, 없으면 자동 생성 이메일로. 셋 다 실패하면 `null` 인 채로 간다. 상담사가 없어도 평가는 되고, 결과의 `consultant_id` 만 빈다. ④가 `evaluateCall(...).join()` 이다. `@Async` 메서드를 `join` 으로 동기 호출한다. 들어가면 `evaluateCallInternal` (261줄) 이고 거기서 세 단계로 쪼개진다. ⑤는 대상 상태 마감이다. 결과 ID 가 있으면 `COMPLETED`, 없으면 `SKIPPED`.

④ 안의 세 단계가 이 파일의 설계다. `prepareEvaluation` (484줄) 은 `REQUIRES_NEW` 30초 안에서 중복 검사, 계획과 평가표 로드, 대화 확정, 결과 껍데기 저장을 하고 커밋한다. `runEvaluationLoop` (674줄) 은 `NOT_SUPPORTED` 로 트랜잭션 없이 문항을 돈다. `persistEvaluation` (630줄) 이 다시 `REQUIRES_NEW` 30초 안에서 점수를 합산하고 문항 상세를 붙여 저장한다. 세 메서드 모두 `selfProvider.getObject()` 를 거쳐 호출된다. 자기 자신을 직접 부르면 AOP 가 끼어들지 못해 `propagation` 이 무시되기 때문이다.

### 이 길에 긴 트랜잭션이 없는 이유

AI 호출은 문항당 5초쯤이고 문항이 열이면 50초다. 그 동안 커넥션을 쥐고 있으면 풀이 마른다. 그래서 이 길의 모든 DB 접근은 30초를 넘지 않는 짧은 트랜잭션 조각이고, LLM 을 부르는 구간은 어떤 트랜잭션에도 속하지 않는다. 저장소 규칙 7번(`@Transactional` 에 `timeout`)과 8번(`readOnly` 안에서 외부 I/O 금지)이 겨누는 것이 이 길이다. 메서드마다 붙은 "CRITICAL Rule 8/11" 주석은 그 규칙을 지키려고 코드를 쪼갠 흔적이다.

---

## 7. 문항 하나가 점수가 되기까지

`runEvaluationLoop` 안에서 문항 하나는 `evaluateQuestionAsync` (997줄) 로 들어간다. 여기서 세 가지 질문을 받는다.

이 문항은 어떤 유형인가. `question_type` 이 셋이다. `FINDING` 은 "인사말을 했는가"처럼 있어야 할 말을 찾는 유형이고, `keyword_patterns` 에 적힌 키워드(`안녕하세요|안녕`)를 Java 가 먼저 발화에서 찾는다. 못 찾으면 AI 를 부르지 않고 0점이다. 찾으면 그 발화 주변만 잘라 AI 에게 "맥락이 맞느냐"를 묻는다. `PROHIBITION` 은 반대다. 금지 표현을 못 찾으면 AI 없이 만점이다. `QUALITY` 는 "친절했는가"처럼 전체 대화를 AI 가 읽어야 하는 유형이다. 로컬 문항 131개 중 93개가 `FINDING` 이고 34개가 `QUALITY` 다.

AI 를 몇 번 부르는가. `evaluateWithPromptConsensus` (`AIEvaluationService` 2067줄) 가 `consensus-enabled` 를 본다. 켜져 있으면 같은 프롬프트를 세 번 보내고 점수의 최빈값을 쓰며, 전부 다르면 중앙값이다. dev 와 prod 는 켜져 있고 local 은 비용 때문에 꺼져 있다. 그래서 같은 통화를 로컬과 dev 에서 평가하면 점수가 다를 수 있다.

점수는 어떻게 합치는가. `persistEvaluation` 에 식이 있다.

```
문항 점수 = similarity_score / 100 × points
총점      = Σ 문항 점수 (반올림)
합격      = 총점 / max_score × 100 >= 70      // PASS_THRESHOLD = 70.0 (EvaluationService 55줄)
```

4절 4번 쿼리의 행이 그대로 이 식이다. 로컬 결과 288번은 7문항, 110점 만점에 80점, 72.7% 로 합격이다. 그 밑의 284번은 68점, 61.8% 로 떨어졌다. 지금 코드는 불합격이면서 `FAIL` 문항이 있으면 `coaching_status` 를 `UNHANDLED` 로 세우는데, 로컬의 7월 결과들은 이 컬럼이 비어 있다.

문항에는 예외가 둘 더 있다. `skip_yn` 이 켜진 문항은 AI 없이 만점이고, 연동 문항(`evaluation_question_link`)은 대표 문항의 결과를 복사한다. 그래서 루프가 2패스다. 대표와 독립 문항을 먼저 돌고, 연동 문항은 그 결과를 베낀다. 로컬에는 연동이 한 건도 없고 조건부 정답지(`question_answer_variant`)는 두 건이다.

---

## 8. 입구 셋과 출구 넷 — 다음 단계로 가는 다리

5절과 6절은 스케줄러에서 들어오는 길이었다. 입구는 둘 더 있다.

화면에서 수동으로. `POST /api/evaluation-executions/manual` 과 `/group` 이 `EvaluationExecutionServiceImpl` 의 `executeManualBatch` · `executeConsultantGroup` 을 부른다. 실행을 만드는 방식은 같고 `batchStarter` 로 들어가는 것도 같다. `POST /api/evaluation-schedules/{id}/trigger` 는 스케줄러의 `triggerScheduleNow` (846줄) 를 부르는데, 이것은 `executeScheduledDirect` 를 그대로 쓴다.

STOMP 로 통화 종료가 올 때. `EvaluationEventListener` 67줄의 `@MessageMapping("/stt/event")` 다. 1단계에서 "평가는 `SttCallCompletedEvent` 로 시작하지 않는다"고 했는데 그 말은 지금도 맞다. 이 리스너는 Spring 이벤트가 아니라 WebSocket 메시지를 직접 받는다. 종료(`E`) 이벤트가 오면 내선번호로 상담사를 찾아 `evaluateCall` 을 바로 부른다. 계획도 실행도 거치지 않는 레거시 길이다. 10월 3일 계약이 붙어서, 원천 키가 실린 메시지는 REST 와 같은 `STTService` 멱등 경로로 저장한 뒤 종료 발행을 실제로 한 경우에만 평가를 한 번 시작한다.

출구는 넷이다. 평가 한 건이 끝나면 `webSocketMessagingService` 가 진행률을 화면에 쏘고, 알림센터에 `EVALUATION_COMPLETED` 행이 생기고, 웹훅 발행기가 `publishEvaluationCompleted` 를 부른다. 배치 전체가 끝나면 `AiModuleTriggerEvent(AI_EVALUATION)` 이 발행되어 워크플로우(6단계 `orchestration`)의 트리거가 된다. 평가표에 `workflow_id` 가 박혀 있으면 아예 배치 프로세서가 `processTargetWithOrchestration` 으로 갈아타서 문항 루프 대신 워크플로우를 돌린다. 그 길은 6단계까지 미룬다.

3단계 `recording` 과 `sttanalytics` 로 가는 다리는 3절의 `source` 다. `ACS` 와 `EXTERNAL_SYNC` 대상이 어디서 어떻게 만들어지는지가 3단계의 첫 질문이다.

---

## 9. 함정 모음

1. **`next_execution_at` 이 과거면 바로 돈다.** 4절 1번 쿼리를 먼저 친다. 시간대 문의의 절반이 여기서 끝난다.
2. **`DATA_READY` 만 고른다.** 대상이 `PENDING` 이면 발화가 없는 것이고, `IN_PROGRESS` 면 누가 집어 간 것이다. 서버가 죽어 `IN_PROGRESS` 에 멈춘 대상은 15분 잡이 60분 정체를 보고 `DATA_READY` 로 되돌린다.
3. **`SCHEDULE` 은 실행 방식이 아니다.** 대상 선택 방식이고 화면 표기는 "연동 대상 기준"이다. 실행 방식은 `execution_mode` 다.
4. **`executeScheduled` 는 죽은 코드다.** 스케줄 길은 `executeScheduledDirect` 다.
5. **`evaluations_per_run` 이 한 번에 집는 상한이다.** 기본 10. 대상이 많으면 cron 횟수만큼 나눠 돈다.
6. **진행 중 실행이 있으면 스케줄이 건너뛴다.** `PENDING` 이나 `IN_PROGRESS` 실행이 하나라도 남아 있으면 그 계획은 영영 돌지 않는다. 9월 24일 사고의 후속 수정이 "시작 실패 시 실행을 `FAILED` 로 닫는다"였던 이유다.
7. **`processBatchAsync` 를 직접 부르면 테스트가 막는다.** `EvaluationBatchStartsAfterCommitTest` 가 가드다. 배치 시작은 `batchStarter.startAfterCommit` 한 곳뿐이다.
8. **`FINDING` 은 키워드가 없으면 AI 를 안 부른다.** 0점의 `ai_reasoning` 에 "키워드 미발견"이 적힌다. AI 가 틀린 게 아니라 `keyword_patterns` 가 틀린 것이다.
9. **local 은 합의 평가가 꺼져 있다.** 같은 통화가 환경마다 다른 점수를 받으면 `consensus-enabled` 부터 본다.

---

## 10. 자가진단

1. `next_execution_at` 은 언제, 무엇을 기준으로 갱신되나.
2. 스케줄 평가가 고르는 대상의 상태값은 무엇이고, 그 상태로 올려 주는 건 누구인가.
3. `evaluation_mode = SCHEDULE` 과 `execution_mode = SCHEDULED` 의 차이를 한 문장으로.
4. `checkAndExecuteSchedules` 가 `executeScheduledDirect` 를 부르는 줄 번호와, 그 안에서 대상 상태가 `IN_PROGRESS` 로 바뀌는 메서드 이름.
5. `EvaluationBatchStarter` 가 생긴 날짜와 그날의 증상.
6. `executeEvaluation` 이 트랜잭션 밖인 이유와, 그 안에서 열리는 짧은 트랜잭션 셋의 메서드 이름.
7. 대화 텍스트 한 줄의 형식과, 화자 라벨을 정하는 컬럼.
8. `FINDING` 문항에서 AI 를 부르지 않는 경우와 그때의 점수.
9. 총점 식과 합격 기준값, 그 상수가 있는 줄.
10. 평가를 시작하는 입구 셋을 파일 이름으로.

여덟 이상이면 3단계로 간다. 3단계는 `recording` 과 `sttanalytics` 다. 이 글 3절의 `source` 네 값 중 `ACS` 와 `EXTERNAL_SYNC` 가 어디서 태어나는지가 거기 첫 질문이다.

---

## 부록: 파일 위치 요약

| 관심사 | 파일 | 줄 |
|---|---|---|
| 대상 상태·출처 enum | `evaluation/entity/EvaluationTarget.java` | 311 |
| 계획 enum 넷 | `evaluation/entity/EvaluationPlan.java` | 486 |
| 스케줄 시계 | `evaluation/entity/EvaluationScheduleConfig.java` | 329 |
| 실행 대상 쿼리 (`next_execution_at`) | `evaluation/repository/EvaluationScheduleConfigRepository.java` | 76~83 |
| 폴링 · 직접 실행 · 정체 정리 · 락 | `evaluation/service/impl/EvaluationSchedulerServiceImpl.java` | 444 · 640 · 168 · 892 |
| 커밋 뒤 배치 시작 | `evaluation/service/impl/EvaluationBatchStarter.java` | 110 |
| 배치 루프 | `evaluation/service/impl/EvaluationBatchProcessorImpl.java` | 103~283 · 922 |
| 평가 한 건 · 세 단계 트랜잭션 | `evaluation/service/EvaluationService.java` | 820 · 484 · 674 · 630 |
| 문항 유형 분기 | 같은 파일 | 997~1120 |
| 합의 평가 · 프롬프트 | `evaluation/service/AIEvaluationService.java` | 2067 |
| 대상 준비 상태 전환 | `evaluation/service/impl/EvaluationReadinessServiceImpl.java` | 80 |
| STT 자동 수집 | `evaluation/service/impl/EvaluationTargetCollectServiceImpl.java` | 120 · 235 |
| STOMP 입구 | `evaluation/listener/EvaluationEventListener.java` | 67 |
| 수동 실행 API | `evaluation/controller/EvaluationExecutionController.java` | 383 |
| 설정값 (배치 20 · 폴링 60초 · 락 30분 · 정체 60분) | `application.yml` | `evaluation.execution.*` |
| 화면 | `web-react/src/pages/evaluation-plan` · `evaluation-target` · `evaluation-result` · `eval-form` | — |

*문서 끝*
