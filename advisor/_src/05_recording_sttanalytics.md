# recording · sttanalytics — 데이터 인입과 분석

> 통화가 바깥 DB 에서 어떻게 들어오고, 파일 더미가 어떻게 상담유형으로 분류되는가
> 작성 2026-10-12 · 기준 커밋 `f06317ca47` · 로컬 DB 실측
> 선행: 2단계 evaluation (자가진단 여덟 문항 이상)

---

## 0. 이 단계의 목표

녹취 수집 실행 이력 테이블을 열었더니 26,312줄이 있었다. 로컬 DB 다. 누가 로컬에서 2만 번을 돌렸나 싶어 스케줄별로 세어 보니 1번 스케줄 혼자 15,453줄이었고, cron 이 `0 0/2 * * * ?` 였다. 1월 22일부터 4월 9일까지 2분마다 한 번씩, 켜 둔 노트북이 혼자 고객사 DB 흉내를 낸 테이블을 긁고 있었던 것이다. 8,315줄은 실패였고 22줄은 아직도 `RUNNING` 이다.

이 단계는 두 모듈을 한 글에 묶는다. `recording` 은 바깥 DB 와 파일 서버에서 통화를 안으로 들여오는 길이고, `sttanalytics` 는 들여온 텍스트 파일 더미를 AI 로 상담유형 분류하는 공장이다. 둘 다 1단계 stt 의 강어귀를 거치지 않는다. 그게 이 글에서 가장 먼저 고쳐 둘 그림이다. 2단계 `evaluation_target` 의 `source` 에 있던 `EXTERNAL_SYNC` 가 어디서 태어나는지도 여기서 답이 난다.

### 7월 가이드 뒤에 바뀐 것

| 항목 | 7월 27일 | 지금 |
|---|---|---|
| `recording` Java 파일 | 112 | 112 (커밋 5개, 구조 그대로) |
| `sttanalytics` Java 파일 | 138 | 153 (커밋 17개) |
| 수집기 종류 | 7 | 7 (`ORACLE` `MARIADB` `API` `FTP` `SFTP` `SCP` `LOCAL`) |
| `@Scheduled` | — | `recording` 1 · `sttanalytics` 1 |

`recording` 은 두 달 반 동안 거의 손을 타지 않았다. 7월 31일 외부 녹취 시스템 연동용 `public_id` 가 들어온 것과 8월 7일 화자 판정 컬럼 이관이 전부다. `sttanalytics` 는 10월 초에 원천 이벤트 멱등과 분류 투영 순서를 손봤다. 그래서 이 글은 `recording` 을 깊게, `sttanalytics` 는 지도만 그린다.

---

## 1. 두 모듈이 하는 일 (한 문장씩)

`recording` 은 고객사 DB 의 뷰 두 개(통화 목록과 문장 목록)를 주기적으로 읽어 우리 `stt_events` 와 `stt_messages` 에 직접 써 넣고, 평가 대상 뷰를 읽을 때는 `evaluation_target` 에 써 넣은 뒤 "다 넣었다"는 이벤트 하나를 띄운다.

`sttanalytics` 는 외부 STT 시스템이 떨군 rx/tx 텍스트 파일을 폴더째 업로드 받아 통화 단위로 합치고, 작업 하나를 만들어 통화를 50건씩 묶어 AI 에 상담유형을 묻고, 결과를 MongoDB 와 포인터 테이블에 남겨 추이 통계를 낸다.

```
 [recording]
 고객사 Oracle/MariaDB ── 60초 폴링 ──▶ RecordingScheduler ──▶ CollectionEngine ──▶ 수집기 7종 중 하나
      VW_RECORDINGINDEX + VW_RESULTSENTENCE ──(STT)──────────────▶ stt_events · stt_messages   ← 강어귀를 거치지 않는다
      VW_INSPECTION_TARGET 류 ──────────────(EVALUATION_TARGET)──▶ evaluation_target (source=EXTERNAL_SYNC, PENDING)
      끝나면 RecordingSyncCompletedEvent ──▶ evaluation 이 PENDING → DATA_READY 로 올린다

 [sttanalytics]
 rx/tx 텍스트 파일 더미 ──POST /folders/upload──▶ folder · call · utterance
      ──POST /jobs──▶ job ──▶ chunk(50건) ──▶ 전략(SINGLE/GROUPED/EXTERNAL_BATCH) ──▶ classifyCall ──▶ 이벤트
      ──▶ ClassificationStatisticsListener ──▶ MongoDB stt_classification_result + call_classification 포인터
```

1단계에서 stt 를 강어귀라고 불렀다. 그 그림에 물길 하나를 더 그어야 한다. `recording` 은 강어귀 옆에 따로 판 운하다. 바깥 DB 의 물을 저수지(`stt_messages`)로 곧장 흘려 넣고, 강어귀의 필터도 실시간 방송도 종료 이벤트도 지나지 않는다. 그래서 운하로 들어온 통화는 화면에 실시간으로 뜨지 않았고, `SttCallCompletedEvent` 구독자들은 그 통화가 끝난 줄 모른다. `OracleSyncService.processChunk` (625줄) 가 `sttEventRepository.saveAll` 과 `sttMessageRepository.saveAll` 을 직접 부르는 자리가 그 운하의 입구다.

---

## 2. 읽는 순서 (8개 파일, 이 순서대로)

| # | 파일 | 줄 수 | 읽는 법 |
|---|---|---|---|
| 1 | `recording/entity/DataSource.java` | 416 | 상단 컬럼과 enum 넷. 평가 2단계의 `EvaluationPlan` 만큼 설정이 많다 |
| 2 | `recording/entity/RecordingSchedule.java` | 112 | 전부. 90~111줄 메서드 셋이 스케줄의 전부다 |
| 3 | DB SELECT | — | 4절 쿼리 넷 |
| 4 | `recording/scheduler/RecordingScheduler.java` | 388 | 60~100줄 `pollSchedules` 와 117~199줄 `executeScheduleAsync`, 237~316줄 `completeExecution` |
| 5 | `recording/collector/CollectionEngineImpl.java` | 323 | 37~137줄 `collect` 만. 수집기 선택이 여기서 난다 |
| 6 | `recording/service/OracleSyncService.java` | 2,086 | 119~300줄 `syncFromOracle` 과 625~700줄 `processChunk` 만 |
| 7 | `recording/service/sync/EvaluationTargetSyncStrategy.java` | 520 | 83~213줄 `processChunk` 와 260~298줄 `buildEvaluationTarget` |
| 8 | `sttanalytics/package-info.java` 와 `service/impl/SttAnalysisJobServiceImpl.java` | 18 · 1,308 | 머리 주석 전부, 그다음 513~619줄 `runJob` 과 660~734줄 `processChunk` |

6번이 이천 줄이다. 겁먹지 말라는 말을 이제 세 번째 쓴다. 이 파일은 Oracle 과 MariaDB 를 같은 코드로 다루느라 길어진 것이지 흐름이 복잡해서 길어진 게 아니다. 메서드 둘만 따라가면 된다.

---

## 3. entity — 두 모듈의 "명사"

### 3.1 `recording` — 명사 셋

| 엔티티 | 테이블 | 한 줄 | 로컬 행 수 |
|---|---|---|---|
| `DataSource` | `recording_data_source` | 어디서(호스트·뷰 이름) · 무엇을(STT 인지 평가 대상인지) · 어디까지 읽었나 | 9 |
| `RecordingSchedule` | `recording_schedule` | 그 데이터소스를 언제(cron) 읽나. `next_execution_time` 이 시계 | 7 |
| `ExecutionHistory` | `recording_execution_history` | 한 번 읽은 기록. 건수와 소요 시간과 에러 | 26,312 |

나머지 셋은 비어 있다. `RecordingData` (`recording_data`) 는 파일 수집기용 메타 테이블인데 로컬에 0건이고, 수집기 일곱 중 어느 것도 이 테이블에 쓰지 않는다. `EvaluationQueue` 는 평가 계획이 생기기 전 녹취 수집 직후 평가를 걸던 대기열이고, 그 스케줄 둘은 주석 처리된 채 남아 있다. `StorageConfig` 는 파일 저장소 용량 설정이다. 셋 다 이번에는 건너뛴다.

`DataSource` 의 enum 넷이 분기의 전부다.

| 컬럼 | 값 | 뜻 |
|---|---|---|
| `type` | `ORACLE` `MARIADB` `API` `FTP` `SFTP` `SCP` `LOCAL` | 수집기 일곱 중 무엇을 쓰나. 앞의 둘은 DB→DB 동기화, 나머지는 파일 |
| `sync_target_type` | `STT` / `EVALUATION_TARGET` | 통화 문장을 넣나, 평가 대상을 넣나 |
| `sync_direction` | `IMPORT` / `EXPORT` | 들여오나, 평가 결과를 고객사 DB 로 내보내나 |
| `sync_key_mode` | `INCREMENTAL` / `FILTER` | 어디까지 읽었는지를 키 값으로 기억하나, 조건으로 거르나 |

`ORACLE` 과 `MARIADB` 는 수집기 클래스가 다르지만 둘 다 `OracleSyncService.syncFromOracle` 을 부른다. 이름에 Oracle 이 박혀 있지만 연결 빌더가 타입을 보고 갈라질 뿐 로직은 하나다. 이 이름이 9절 함정 하나의 원인이기도 하다.

### 3.2 `sttanalytics` — 명사 일곱, 셋만

| 엔티티 | 테이블 | 한 줄 |
|---|---|---|
| `SttAnalysisFolder` → `SttAnalysisCall` → `SttAnalysisUtterance` | `stt_analysis_folder` · `_call` · `_utterance` | 업로드한 폴더, 그 안의 통화, 통화의 발화 |
| `SttAnalysisJob` → `SttAnalysisChunk` | `stt_analysis_job` · `_chunk` | 분류 작업 하나와 50건씩 자른 조각 |
| `SttAnalysisCallClassification` | `stt_analysis_call_classification` | 통화별 최신 분류 포인터. 원장은 MongoDB |

`stt_analysis_utterance` 는 1단계의 `stt_messages` 와 닮았지만 다른 테이블이다. 화자 컬럼 이름이 `speaker` 고 값이 rx/tx 파일에서 왔다. 두 테이블 사이에 외래키도 없고 조인도 없다. 이 모듈은 우리 저수지의 물이 아니라 바깥에서 가져온 상자를 다룬다.

상태는 넷을 외우면 된다. 작업은 `PENDING → RUNNING → COMPLETED / FAILED / PAUSED`, 조각은 `PENDING → RUNNING → COMPLETED`(외부 배치면 중간에 `SUBMITTED_REMOTE`), 통화는 `UNCLASSIFIED → CLASSIFYING → CLASSIFIED`, 전략은 `SINGLE / GROUPED / EXTERNAL_BATCH`.

---

## 4. DB 실습 — 코드 전에 데이터부터

```bash
docker exec -it mariadb mariadb -u <계정> -p local_db
```

```sql
-- 1) 데이터소스 아홉. 무엇을 어디서 읽는가
SELECT id, name, type, enabled, sync_target_type, sync_direction, sync_key_column,
       oracle_master_table, oracle_detail_table, last_sync_time, total_synced_count
FROM recording_data_source;

-- 2) 스케줄의 시계
SELECT id, data_source_id, name, cron_expression, enabled, last_execution_time,
       next_execution_time, last_execution_status, NOW() AS now
FROM recording_schedule;

-- 3) 이 글의 첫 문단
SELECT schedule_id, status, COUNT(*) n, MIN(started_at), MAX(started_at)
FROM recording_execution_history GROUP BY 1, 2 ORDER BY 1, 2;

-- 4) 가장 최근 실패의 이유
SELECT id, schedule_id, status, started_at, duration_ms, total_records, success_records, error_message
FROM recording_execution_history ORDER BY id DESC LIMIT 5;
```

1번은 아홉 줄이다. Oracle 넷(하나는 꺼짐), MariaDB 다섯. `sync_target_type` 은 `STT` 여섯에 `EVALUATION_TARGET` 셋이고 전부 `IMPORT` 다. `oracle_master_table` 에 `VW_RECORDINGINDEX` 가 여섯 번 나온다. 고객사 Oracle 의 뷰 이름인데, 로컬 MariaDB 에 같은 이름의 테이블을 만들어 두고 흉내를 낸 것이다. `SHOW TABLES LIKE 'VW_%'` 를 쳐 보면 둘이 나온다.

2번은 일곱 줄 중 셋만 켜져 있다. 7번은 매년 7월 14일 한 번 도는 테스트용이라 다음이 2027년이고, 8번과 9번은 매월 1일 09:00 이다. 둘 다 `last_execution_status` 가 `FAILED` 다. 4번이 그 이유를 보여 준다. 9월 1일과 10월 1일 두 번 다 같은 메시지로 죽었다. `bad SQL grammar [SELECT COUNT(*) FROM VW_RECORDINGINDEX A WHERE A.CALL_DATETIME > TO_TIMESTAMP(?, ...)]`. MariaDB 에 Oracle 의 날짜 함수를 보낸 것이다. 9절에서 왜 그렇게 되는지 짚는다.

3번이 첫 문단이다. 2분 cron 의 1번 스케줄이 15,453줄, 3분 cron 의 2번이 10,511줄. 그 둘이 1월 22일에 시작해 4월 9일에 멈췄다. `RUNNING` 22줄은 2월과 3월 것이다. 서버가 그 사이에 몇 번 죽었다는 뜻이고, 이 모듈에는 그걸 치워 주는 잡이 없다. 2단계의 `cleanupStaleExecutions` 같은 것이 여기에는 없다.

`sttanalytics` 쪽 테이블 일곱은 로컬에 전부 0건이다. 이 기능을 로컬에서 써 본 적이 없다는 뜻이다. 그래서 6절은 데이터 없이 코드와 주석만으로 그린다.

> 💡 **운하로 들어온 통화를 1단계 쿼리로 찾아보자.** `stt_events` 에서 `created_at` 이 같은 초에 S 와 E 가 같이 찍힌 통화가 그것이다. `createSttEventsForBatch` 가 시작·종료 이벤트를 한 번에 만들어 `now` 를 둘 다에 적기 때문이다. 실시간으로 들어온 통화는 둘 사이가 통화 시간만큼 벌어져 있다.

---

## 5. recording — `pollSchedules` 에서 이벤트 발행까지

### 5.1 `RecordingScheduler` (60~316줄)

2단계의 평가 스케줄러를 봤으면 이 파일은 축소판이다. 60초마다 `pollSchedules` 가 `findSchedulesToExecute(now)` 를 부른다. 조건은 셋뿐이다. `enabled`, `next_execution_time IS NOT NULL`, `next_execution_time <= now`. 락이 없다. 서버가 둘이면 둘 다 같은 스케줄을 집는다. `OracleSyncService` 가 데이터소스 단위로 `activeSyncIds` 라는 메모리 맵으로 중복을 막지만 그건 한 JVM 안에서만 통한다.

걸린 스케줄마다 `executeScheduleAsync(scheduleId)` 로 넘긴다. `@Async("recordingTaskExecutor")` 고 풀은 다섯이다. 이 메서드에는 `@Transactional` 이 없고, 주석이 2단계와 같은 말을 한다. 수집이 오래 걸리면 커넥션이 샌다. 그래서 `fetchScheduleWithDataSource` 와 `createExecutionHistory` 와 `completeExecution` 이 각자 짧은 트랜잭션이고, 가운데 `collectionEngine.collect(schedule, history)` 는 트랜잭션 밖이다.

`completeExecution` (237줄) 이 결과를 적는다. 이력에 건수와 시간을 쓰고, 스케줄의 `last_execution_time` 과 `next_execution_time` 을 갱신한다. `next_execution_time = cron.next(지금)` 이다. 2단계와 같은 규칙이고 같은 함정이다. 그다음 알림센터에 한 줄 남기고, 들여오기 방향이고 성공이거나 부분 성공이면 `RecordingSyncCompletedEvent` 를 발행한다. 이 이벤트의 구독자는 하나다. 2단계에서 본 `EvaluationReadinessListener` 가 받아서 `PENDING` 대상을 `DATA_READY` 로 올린다.

### 5.2 `CollectionEngineImpl.collect` (37~137줄) — 갈림길 셋

첫 갈림길은 `sync_direction`. `EXPORT` 면 수집기를 고르지 않고 `ExportSyncService` 로 바로 간다. 평가 결과를 고객사 DB 에 써 주는 반대 방향이다. 둘째는 `type.isDatabase()`. DB 타입이면 저장 경로 검증을 건너뛰고, 파일 타입이면 저장 디렉토리를 먼저 확인한다. 셋째가 `collectorFactory.getCollector(type)`. 팩토리는 Spring 이 주입한 `IDataCollector` 일곱을 `getSupportedType()` 기준으로 맵에 넣어 두고 꺼내 준다. 새 타입을 붙이려면 enum 에 값 하나, 구현체 하나면 된다.

`OracleDataCollector` 와 `MariaDbDataCollector` 는 둘 다 한 줄짜리다. `oracleSyncService.syncFromOracle(dataSource.getId())`. 그래서 6번 파일로 간다.

### 5.3 `OracleSyncService.syncFromOracle` (119줄) — 운하의 본체

`activeSyncIds.putIfAbsent` 로 같은 데이터소스의 동시 실행을 막고 `doSyncFromOracle` 로 들어간다. 거기서 첫 번째로 보는 것이 `sync_target_type` 이다. `EVALUATION_TARGET` 이면 `syncEvaluationTargetFromOracle` 로 빠지고, 그 안에서 7번 파일 `EvaluationTargetSyncStrategy` 가 일한다. `STT` 면 아래로 계속 간다.

STT 길은 이렇다. 컬럼 매핑(`column_mapping` JSON)을 읽고, 바깥 DB 에 `JdbcTemplate` 을 연다. `countMasterRecords` 로 읽을 통화 수를 센다. 0 이면 바로 끝. 아니면 마스터 뷰를 페이지로 읽으면서 페이지마다 `sttEventRepository.findExistingCallIds` 로 이미 있는 통화를 거르고, 페이지를 다시 청크로 잘라 `processChunk` 를 부른다. 청크 하나가 트랜잭션 하나다. 다 돌면 `last_sync_time` 과 `last_sync_key_value` 를 데이터소스에 적는다. 다음 실행은 거기서부터 읽는다.

`processChunk` (625줄) 안에서 통화 한 건은 이렇게 된다. 마스터 한 행으로 `STTEvent` 둘을 만든다. `S` 하나, `E` 하나. `E` 의 시각은 `S` 에 `talkTime` 초를 더한 값이다. 그다음 상세 뷰에서 그 통화의 문장을 전부 읽어 `STTMessage` 로 만든다. 화자는 `RXTX_KIND` 컬럼이다. 1 이면 `RX`(고객), 2 면 `TX`(상담사), 9 면 `MIX`. `mapChannelType` (1386줄) 이 그 표다. 그 값을 `call_type` 과 `channel_type` 둘 다에 넣는다. 1단계에서 "`call_type` 이 정답이고 `channel_type` 은 폐기 컬럼"이라고 했는데, 8월 7일 커밋이 이 자리를 고치면서 남긴 주석이 그 사연을 그대로 적어 두었다. 예전에는 통화 방향(IN/OUT)을 화자 칸에 넣어서 화면에 화자가 안 떴다.

### 5.4 `EvaluationTargetSyncStrategy.processChunk` (83줄) — 2단계의 `EXTERNAL_SYNC` 가 태어나는 자리

행 하나가 `EvaluationTarget` 하나다. `buildEvaluationTarget` (260줄) 을 보면 `source(EXTERNAL_SYNC)` 와 `evaluationStatus(PENDING)` 이 박혀 있다. 2단계 3절의 상태 그림에서 맨 왼쪽 `PENDING` 이 여기다. `externalKey` 는 고객사 원본 키고 중복 판정의 기준이다. 콜 ID 는 `callIds` 컬럼이 있으면 쉼표나 파이프로 잘라 `EvaluationTargetCall` 여러 줄로, 없으면 `callId` 하나로 한 줄 만든다. 2단계에서 "콜 ID 는 자식 테이블에 1:N" 이라고 쓴 이유가 이 분기다.

저장은 `saveAll` 두 번이다. 대상을 먼저 저장하고, 돌려받은 managed 엔티티를 외부 키로 다시 찾아 콜 매핑에 꽂은 뒤 매핑을 저장한다. 그 뒤 `completeExecution` 이 이벤트를 띄우고, `EvaluationReadinessListener` 가 `stt_messages` 에 발화가 있는 대상만 `DATA_READY` 로 올리면, 2단계의 60초 폴링이 그걸 집어 간다. 운하 둘이 저수지에서 만나는 지점이 이것이다. 하나는 발화를, 하나는 평가 대상을 넣고, 발화가 먼저 와 있어야 대상이 자격을 얻는다.

---

## 6. sttanalytics — 지도만

이 모듈은 5월 초에 spec 042 로 한 번에 지어졌고 `package-info.java` 열여덟 줄에 설계 원칙이 다 적혀 있다. 그 원칙이 2단계에서 본 것과 같다. 중첩 `REQUIRES_NEW` 0건, `readOnly` 안 LLM 호출 0건, 모든 트랜잭션에 `timeout`. 그 밑에서 길은 세 토막이다.

**들이기.** `POST /api/sttanalytics/folders/upload` 가 파일 묶음을 받는다. `SttFileIngestionServiceImpl` (1,678줄) 이 인코딩을 맞추고, 파일명에서 통화 키와 내선번호를 뽑고, 내선번호별로 묶어 스레드 다섯으로 나눠 각자 트랜잭션에서 `stt_analysis_utterance` 에 넣는다. 같은 (통화, 시각, 화자, 문장) 4-튜플은 버린다. 폴더의 `call_count` 를 올리고 끝. 업로드가 끝나면 기본값으로 분류 작업을 바로 만든다(`autoStartJob=true`).

**자르기.** `POST /api/sttanalytics/jobs` 가 `SttAnalysisJobServiceImpl.createJob` (200줄) 이다. 폴더에 든 통화 ID 를 모아 50건씩 `stt_analysis_chunk` 로 자른다(외부 배치 전략이면 4,000건). 그다음 `runJobAsync` 로 넘긴다. `runJob` (513줄) 은 트랜잭션 밖에서 조각을 하나씩 집는데, 집는 방법이 `tryClaimChunk` 다. UPDATE 한 줄로 `claimed_by` 에 워커 ID 를 적고 1건이 바뀌었을 때만 내 것이다. 2단계 스케줄 락과 같은 수법이고, 서버가 여럿이어도 한 조각은 한 번만 처리된다. 조각 안에서는 `BatchStrategy` 가 일한다. `SINGLE` 은 통화 하나에 AI 호출 하나, `GROUPED` 는 여러 통화를 한 프롬프트에 묶기, `EXTERNAL_BATCH` 는 vLLM 이나 OpenAI 의 배치 API 에 던지고 30초 폴링 워커가 결과를 가져오는 방식이다.

**매기기와 남기기.** `CounselTypeClassificationServiceImpl.classifyCall` (154줄) 이 통화 하나를 분류한다. 발화를 따로 트랜잭션에서 읽어 커넥션을 돌려주고, 프롬프트에 상담유형 카탈로그와 예시를 끼워 AI 를 부르고, 신뢰도가 공급자별 문턱(설정값)을 넘으면 `counseltype` 모듈의 `autoRegisterIfMissing` 으로 새 유형을 등록한다. 1단계 보너스에서 본 `counseltype` 이 여기 손님이다. 결과는 `SttClassificationCompletedEvent` 로 나가고, `ClassificationStatisticsListener` (464줄) 가 커밋 뒤에 받아 MongoDB `stt_classification_result` 에 한 건 적고, `stt_analysis_call_classification` 포인터를 갱신하고, 통화 상태와 작업 카운터를 올리고, STOMP 로 진행률을 쏜다. 그 Mongo 컬렉션을 `SttAnalyticsController` 열한 개 엔드포인트가 읽어 추이·시간대·예측·pptx 보고서를 만든다.

이 모듈이 stt 모듈과 어디서 만나는지 찾아보았다. 만나지 않는다. `sttanalytics` 안에 `stt.event` 를 import 하는 파일이 없다. 1단계 글에 "`sttanalytics` 가 stt 이벤트를 받아서 분석한다"고 쓴 문장은 틀렸고, 이 글을 쓰면서 고쳤다. 상자 공장은 강에 닿아 있지 않다.

---

## 7. 다음 단계로 가는 다리

4단계는 `ai` 모듈 1,227개 파일 중 세 패키지다. 이 글에서 AI 를 부르는 자리를 둘 봤다. 2단계의 `AIEvaluationService` 는 `aiModelFallbackClient` 를, 이 글의 `classifyCall` 은 `aiOrchestrator.execute` 를 부른다. 둘 다 `ai/execution/` 으로 들어간다. 프롬프트는 둘 다 `ai/prompt/` 의 템플릿(`PromptType.COUNSEL_TYPE_CLASSIFY`, `EVALUATION_OUTPUT_CONTRACT`)에서 온다. 모델을 고르고 실패하면 다음 모델로 넘기는 건 `ai/routing/` 이다. 4단계는 이 셋을 연다. 나머지는 지도만 본다.

---

## 8. 함정 모음

1. **MariaDB 데이터소스에 `last_sync_time` 이 생기면 죽는다.** `countMasterRecords` 의 레거시 STT 길(788줄)이 `sync_key_column` 이 없고 `last_sync_time` 이 있으면 `TO_TIMESTAMP(?, 'YYYY-MM-DD HH24:MI:SS')` 를 붙인다. Oracle 전용 함수다. 그 값이 비어 있으면 조건 없이 읽어 성공하고, 값이 들어가면 그다음부터 매번 `bad SQL grammar` 다. 로컬 8번·9번 스케줄은 7월에 성공하다가 8월 1일부터 석 달째 같은 메시지로 죽고 있다. 피해 가는 길은 `sync_key_column` 을 지정하는 것이다. 10번 데이터소스는 `CALL_DATETIME` 을 키로 걸어 653건을 멀쩡히 넣었다.
2. **`RUNNING` 은 아무도 치우지 않는다.** 수집 도중 서버가 죽으면 이력이 `RUNNING` 으로 남고, 로컬에 22줄이 그렇다. 2단계와 달리 정체 정리 잡이 없다. 다만 다음 실행을 막지는 않는다. 평가 쪽은 진행 중 실행이 있으면 건너뛰지만 여기는 그런 가드가 없다.
3. **스케줄에는 락이 걸리지 않는다.** `findSchedulesToExecute` 에 `lock_owner` 조건이 없다. 서버 둘이 같은 스케줄을 동시에 집을 수 있고, 데이터소스 단위 중복 방지는 JVM 메모리 맵이라 서버를 넘지 못한다.
4. **운하는 강어귀를 거치지 않는다.** 동기화로 들어온 통화는 `SttIngestFilter` 도, 실시간 방송도, `SttCallCompletedEvent` 도 없다. 상담보조·워크플로우 트리거가 그 통화에 대해 아무것도 하지 않는 것이 정상이다.
5. **`next_execution_time` 은 `cron.next(지금)`.** 2단계와 같은 규칙이다. 서버가 죽었다 뜨면 밀린 스케줄이 시간대와 무관하게 한 번 돈다.
6. **2분 cron 을 로컬에 켜 두면 하루 720줄이 쌓인다.** 1번 스케줄이 그렇게 15,453줄을 만들었다. 이력 테이블에 보존 정리가 없다.
7. **`recording_data` 는 쓰는 곳이 없다.** 수집기 일곱 중 아무도 이 테이블에 쓰지 않는다. 화면의 "녹취 데이터" 목록이 비어 있어도 수집이 안 된 게 아니다. 들어온 통화는 `stt_events` 에서 센다.
8. **`EvaluationQueue` 는 폐기된 길이다.** `EvaluationTriggerServiceImpl` 의 `@Scheduled` 둘이 주석 처리되어 있고, 메서드는 0 을 돌려준다. `/api/recording/evaluation` 엔드포인트 열셋이 아직 열려 있지만 평가는 2단계의 계획이 한다.
9. **`sttanalytics` 는 `stt_messages` 를 읽지 않는다.** 자기 테이블 `stt_analysis_utterance` 만 본다. 실시간으로 들어온 통화를 상담유형 분류하려면 이 모듈이 아니라 `counseltype` 의 자동 분류 쪽을 봐야 한다.

---

## 9. 자가진단

1. `recording` 이 `stt_messages` 에 쓰는 메서드와 줄 번호. 그 길에 없는 세 가지.
2. `sync_target_type` 두 값이 각각 어느 테이블에 쓰는가.
3. `EXTERNAL_SYNC` 대상이 태어날 때의 `evaluation_status` 와, 그것을 `DATA_READY` 로 올리는 이벤트 이름.
4. 수집기 일곱 중 둘이 같은 서비스를 부른다. 그 둘과 그 서비스.
5. `RXTX_KIND` 1·2·9 가 각각 무엇이 되나.
6. 로컬 8번·9번 스케줄이 매월 1일 실패하는 이유와 피해 가는 설정.
7. `recording_execution_history` 에 `RUNNING` 22줄이 남아 있는 이유.
8. `sttanalytics` 가 통화를 몇 건씩 자르고, 조각을 집는 방법은 무엇인가.
9. 분류 결과의 원장은 어디고 포인터는 어디인가.
10. `sttanalytics` 와 `stt` 모듈이 만나는 지점.

여덟 이상이면 4단계로 간다. 4단계는 `ai` 의 `execution` · `prompt` · `routing` 이다. 이 글의 `classifyCall` 과 2단계의 `evaluateWithPrompt` 가 거기서 같은 문을 지난다.

---

## 부록: 파일 위치 요약

| 관심사 | 파일 | 줄 |
|---|---|---|
| 데이터소스 설정 enum 넷 | `recording/entity/DataSource.java` | 416 |
| 스케줄 시계 (`shouldExecute` · `updateExecutionResult`) | `recording/entity/RecordingSchedule.java` | 90 · 107 |
| 60초 폴링 · 비동기 실행 · 완료 처리 | `recording/scheduler/RecordingScheduler.java` | 60 · 117 · 237 |
| 갈림길 셋 (EXPORT · DB/파일 · 수집기 선택) | `recording/collector/CollectionEngineImpl.java` | 37~137 |
| 수집기 팩토리 · 구현 일곱 | `recording/collector/DataCollectorFactory.java` · `collector/impl/` | 91 |
| STT 동기화 본체 · 청크 · 화자 표 · Oracle 전용 SQL | `recording/service/OracleSyncService.java` | 119 · 625 · 1386 · 788 |
| 평가 대상 동기화 | `recording/service/sync/EvaluationTargetSyncStrategy.java` | 83 · 260 |
| 완료 이벤트 → 2단계 | `recording/event/RecordingSyncCompletedEvent.java` → `evaluation/listener/EvaluationReadinessListener.java` | 52 |
| 설정 (폴링 60초 · 풀 5 · 실행 타임아웃 3,600초) | `application.yml` | `recording.*` |
| 모듈 설계 원칙 | `sttanalytics/package-info.java` | 18 |
| 업로드 · 합본 | `sttanalytics/service/impl/SttFileIngestionServiceImpl.java` | 197 · 369 · 929 |
| 작업 생성 · 조각 처리 · 클레임 | `sttanalytics/service/impl/SttAnalysisJobServiceImpl.java` | 200 · 513 · 660 · 734 |
| 통화 하나 분류 | `sttanalytics/service/impl/CounselTypeClassificationServiceImpl.java` | 154 |
| 결과 적재 리스너 (Mongo · 포인터 · 카운터) | `sttanalytics/event/listener/ClassificationStatisticsListener.java` | 464 |
| 전략 셋 | `sttanalytics/strategy/impl/SingleCallStrategy` · `GroupedPromptStrategy` · `ExternalBatchApiStrategy` | 151 · 925 · 485 |
| 화면 | `web-react/src/pages/RecordingDataPage.tsx` · `stt-batch/SttBatchPage.tsx` · `CounselTypeAnalyticsPage.tsx` | — |

*문서 끝*
