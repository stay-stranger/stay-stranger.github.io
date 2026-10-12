# 어드바이저 코드베이스 학습 가이드

> 대상: 처음 이 저장소를 받아 든 개발자
> 최초 작성 2026-07-27 · 전수 재측정 2026-10-12 (커밋 `f06317ca47`)

> 📌 **갱신 요지** 7월에 쓴 초판은 두 달 반 만에 낡았다. Java 파일이 5,810개에서 7,814개로 늘었고, 권한은 역할에서 기능 권한으로 옮겨 갔고, 메뉴의 원본은 프런트에서 백엔드 JSON 으로 넘어갔다. 읽는 순서는 그대로 두고 숫자와 줄 번호는 전부 다시 쟀다. 1단계 stt 는 글 하나로 따로 떼어 냈다.

---

## 0. 시작하기 전에

저장소를 받아 `find` 로 Java 파일을 세어 봤을 때 숫자는 7,814였다. 최상위 패키지만 61개. Flyway 마이그레이션 파일은 1,127개가 쌓여 있었고, React 쪽은 tsx 파일이 1,642개였다. 그 숫자를 보고 나는 "전부 이해하겠다"는 계획을 접었다. 접는 데 오래 걸리지 않았다.

| 항목 | 수량 | 7월 대비 |
|---|---|---|
| Java 파일 | 7,814개 | +2,004 |
| 백엔드 도메인 모듈 (최상위 패키지) | 61개 | +4 |
| Flyway 마이그레이션 | 1,127개 | +589 |
| React 컴포넌트 (tsx) | 1,642개 | +544 |
| React 페이지 (`*Page.tsx`) | 205개 | — |

목표는 다른 것이어야 했다. 이 저장소에서 필요한 자리에 빠르게 도달하는 능력. 지도를 전부 외우는 사람은 없다. 자주 다니는 길 몇 개를 발에 익히고, 나머지는 지도를 꺼내 본다. 이 가이드의 0~2단계가 전체 Java 파일의 9% 남짓인데(671 / 7,814), 현업에서 손대는 일의 대부분이 그 안에서 일어난다.

### 항상 옆에 둘 문서 4개

| 파일 | 용도 |
|---|---|
| `PROJECT_INDEX.md` | 61개 모듈의 한 줄 지도. 길을 잃으면 여기부터 |
| `AGENTS.md` (`CLAUDE.md` 가 이 파일을 가져온다) | 규칙·CRITICAL 인덱스·명령어 |
| `claudedocs/MODULE_ARCHITECTURE.md` | 모듈별 상세 구조 (2026-05 아카이브) |
| `claudedocs/08_backend_services/CODE_REVIEW_CHECKLIST.md` | 지뢰 목록. 코드를 쓰기 전에 읽는다 |

---

## 1. 전체 학습 경로

가장 크고 가장 바쁜 모듈은 `ai` 와 `kms` 와 `agi` 다. 그래서 거기서 시작하면 안 된다. 큰 모듈은 패턴을 보여 주기 전에 사람을 먼저 지치게 한다. 작은 모듈에서 구조를 익히고, 그 구조가 손에 붙은 뒤에 큰 쪽으로 건너간다.

| 단계 | 모듈 | 파일 수 | 목표 | 예상 |
|---|---|---|---|---|
| **0** | `core` → `auth` → `permission` | 289 (137 + 82 + 70) | 인증·권한·응답 규격 | 2~3일 |
| **1** | `stt` (+ `counseltype`) | 65 (+35) | 모듈 구조 패턴 체득 → 별도 글 | 1~2일 |
| **2** | `evaluation` | 282 | 핵심 업무 도메인 | 1주 |
| **3** | `recording` → `sttanalytics` | 265 (112 + 153) | 데이터 인입·분석 | 1주 |
| **4** | `ai` (일부만) | 1,227 중 3개 패키지 | AI 실행 기반 | 3일 |
| **5** | `rag` → `kms` | 1,048 (274 + 774) | 검색·지식 | 2주 |
| **6** | `orchestration` → `agi` | 1,228 (515 + 713) | 워크플로우·자율 에이전트 | 필요 시 |
| 곁가지 | `chat` `assist` `agent` `compliance` | 353 / 286 / 182 / 420 | 필요할 때만 | — |

> 6단계는 가장 어렵고 가장 자주 바뀐다. 필요해지기 전에는 손대지 않는다.

### 모듈 규모·활동량 (참고)

커밋 수는 최근 1년 동안 그 경로를 건드린 커밋만 센 것이다. 파일이 많다고 활발한 건 아니고, `core` 처럼 파일은 적어도 커밋이 몰리는 곳이 있다. 모두가 지나가는 길이라서 그렇다.

| 모듈 | 파일 | 최근 1년 커밋 수 (해당 경로) |
|---|---|---|
| ai | 1,227 | 1,124 |
| kms | 774 | 597 |
| agi | 713 | 615 |
| orchestration | 515 | 454 |
| evaluation | 282 | 228 |
| core | 137 | 665 |
| recording | 112 | 53 |
| stt | 65 | 100 |

---

## 2. 모듈 파헤치기 공통 루틴

61개 모듈은 생김새가 같다. 하나를 여는 법만 익히면 나머지도 같은 방식으로 열린다.

```
1) PROJECT_INDEX.md 에서 해당 모듈 한 줄 설명 확인
2) entity/     — 이 도메인이 다루는 "명사"가 뭔지
3) DB SELECT   — 그 테이블 실제 데이터 10건 눈으로 확인   ← 가장 중요
4) controller/ — 밖에서 뭘 요청할 수 있는지 ("동사")
5) service/impl/ — 관심 있는 메서드 하나만 끝까지 추적
```

세 번째 단계를 건너뛰고 싶은 유혹이 매번 온다. 코드를 읽고 있으면 데이터는 나중에 봐도 될 것 같다. 순서를 바꿔 보면 안다. 실제 행 열 개를 눈으로 본 뒤에 엔티티를 다시 열면, 조금 전까지 추상적이던 컬럼 이름이 전부 아는 얼굴이 되어 있다.

### 표준 디렉토리 구조

모든 모듈이 아래 형태를 따른다.

```
{module}/
  controller/   REST 진입점       @RestController
  service/      인터페이스        IXxxService
  service/impl/ 구현체            XxxServiceImpl
  repository/   DB 접근           JpaRepository
  entity/       테이블 매핑       @Entity
  dto/          요청·응답 객체
  event/        도메인 이벤트
  listener/     이벤트 수신
  scheduler/    주기 실행
```

---

## 3. [0단계] core — 기반

137개 파일 중 읽을 것은 여섯이다. 나머지는 길을 잃었을 때 찾아가면 된다.

### 3.1 `core/dto/ApiResponse.java` (269줄) — 가장 먼저

모든 API 응답이 이 껍데기에 담겨 나간다. `ApiResponse.success()` 와 `badRequest()` 가 컨트롤러마다 반복되기 때문에, 이 파일 하나를 알고 나면 아무 컨트롤러나 열어도 응답부는 읽지 않고 지나갈 수 있다. 목록 응답의 규격인 `core/dto/PageResponse.java` (126줄)를 같이 본다.

### 3.2 `core/config/LocalSecurityConfig.java` (391줄)

"이 URL 은 로그인 없이 되나"라는 질문의 답이 전부 여기 있다. 다만 파일이 셋이다. 프로파일마다 다른 문을 쓴다.

| 파일 | 줄 수 | 적용 프로파일 (`@Profile`) |
|---|---|---|
| `LocalSecurityConfig` | 391 | `local`, `test`, `dev-test` |
| `DevSecurityConfig` | 304 | `dev` |
| `SecurityConfig` | 398 | `prod`, `naver` |

자기 프로파일 것 하나만 본다. 셋을 나란히 놓고 보면 어느 줄이 어느 환경 것인지 금방 섞인다. 볼 곳은 `permitAll()` 이 붙은 열린 경로, 로그인만 요구하는 `authenticated()`, 그리고 `hasRole(...)` 이다. 셋째는 2026-10 기준 `/actuator/**` 한 곳에만 남아 있다. API 경로에 역할을 박지 않는 것이 지금 규칙(CRITICAL 19)이다.

### 3.3 `core/security/JwtAuthenticationFilter.java` (343줄)

처음 이 파일을 열었을 때 나는 요청을 막아 내는 코드를 찾고 있었다. 모든 요청이 지나가는 필터니까 당연히 어딘가에서 막을 거라고 생각했다. 막는 코드는 없었다. 토큰을 꺼내고, 맞는지 보고, 맞으면 `SecurityContext` 에 사람 이름을 적는다. 토큰이 없어도 틀려도 필터는 `filterChain.doFilter()` 를 부르고 길을 비켜 준다. 들여보낼지 말지는 뒤에 선 문, `SecurityConfig` 의 URL 매트릭스가 정한다.

7월에 102줄이던 파일이 지금은 343줄이다. 늘어난 부분은 계정이 삭제되거나 영구 정지된 경우를 토큰 만료와 구분해 처리하는 판정과, ASYNC 디스패치에서 `SecurityContext` 를 정리하는 코드다. 핵심 흐름은 그대로다.

```
① resolveToken(request) 으로 토큰 추출                       (322줄)
     1순위: Authorization: Bearer <토큰>
     2순위: ?token=<토큰> — 단, URL에 /stream 또는 /sse 포함 시에만 허용   (331~335줄)
            (EventSource API 가 커스텀 헤더를 못 보내기 때문)

② tokenProvider.validateToken(token) 검증                     (129줄)

③ 통과 시 userDetailsService.loadUserByUsername() 으로 DB 에서 User 로드   (135줄)
     → SecurityContextHolder 에 인증 정보 저장

④ 사용자 로드 실패(삭제·영구 정지) 시 SecurityContext 를 비우고 미인증 처리
     ※ 토큰 만료와 계정 회수를 구분한다 — 복원은 만료에만 허용

⑤ 토큰이 없거나 틀려도 여기서 막지 않는다 → filterChain.doFilter() 로 그냥 통과
   실제 차단은 SecurityConfig 의 경로 규칙이 담당
```

401 과 403 이 어디서 나오는지 헷갈릴 때마다 ⑤로 돌아오면 된다. 이 필터는 이름을 적는 쪽이고, 문은 다른 데 있다.

### 3.4 `core/security/JwtTokenProvider.java` (376줄)

토큰을 만들고 검증하고 만료시키는 곳이다. 전부 읽을 필요는 없다. 3.3 에서 궁금해진 `validateToken` 과 `getUsername` 만 골라 본다.

### 3.5 `core/exception/GlobalExceptionHandler.java` (1,990줄) — 훑기만

길다. 정독하면 하루가 간다. `@ExceptionHandler` 가 붙은 메서드 이름만 쭉 훑어서 어떤 예외가 어떤 HTTP 응답으로 바뀌는지 감만 잡는다. 이 감이 있으면 나중에 에러 메시지 한 줄로 원인 위치를 거슬러 올라갈 수 있다. 업무 예외의 기본형인 `core/exception/BusinessException.java` 는 26줄이라 금방 본다.

### 3.6 `core/config/DatabaseConfig.java` (516줄) — 훑기만

MariaDB 와 PostgreSQL 과 MongoDB 설정이 한 파일에 있어서 길다. 기억할 건 하나다.

> 🔴 **새 모듈을 만들면 두 곳에 등록한다.** `@EnableJpaRepositories(basePackages = …)` (27줄)와 `setPackagesToScan(PRIMARY_ENTITY_PACKAGES)` (374줄). 빠뜨리면 Repository 빈을 못 찾는다는 메시지가 기동 로그에 뜬다.

### 0단계-core 자가진단

1. `/api/stt/message` 는 왜 인증 없이 호출되나? → 3.2
2. 로그인 후 받은 토큰이 다음 요청에서 어떻게 검증되나? → 3.3
3. SSE 요청은 왜 쿼리파라미터로 토큰을 보내나? → 3.3
4. 토큰이 틀렸을 때 실제로 요청을 막는 건 누구인가? → 3.3 ⑤ + 3.2
5. 새 모듈을 만들었는데 Repository 빈을 못 찾으면? → 3.6

다섯 개에 답할 수 있으면 넘어간다. 핵심 부분만 보면 하루면 된다.

---

## 4. [0단계] auth — 로그인

`auth` 와 `core/security` 는 자주 섞인다. 둘은 다른 시간을 산다. `auth` 는 로그인 그 순간의 일이다. 아이디와 비밀번호를 대조하고 토큰을 발급한다. `core/security` 는 그다음 모든 요청에서 발급된 토큰을 다시 확인한다. 하나는 첫 만남이고 하나는 그 뒤의 매일이다.

| | 역할 |
|---|---|
| `auth` | 로그인 그 자체 — ID/PW 검증, 토큰 발급, SSO |
| `core/security` | 발급된 토큰을 매 요청 검증 |

### 볼 것 (82개 중 3개)

| 파일 | 내용 |
|---|---|
| `auth/controller/AuthController.java` | `/login`(110줄) · `/refresh`(433줄) · `/logout`(759줄) |
| `auth/entity/User.java` | 사용자 테이블. `accountNonLocked`(73줄) · `loginFailCount`(92줄) |
| `auth/entity/LoginAuditLog.java` | 로그인 이력. 계정 잠금을 추적한다 |

구글 연동과 SSO 와 스케줄러는 그 기능을 손댈 때 본다.

### 실습

```bash
# 로그인 호출 (로컬 테스트 계정)
# 본문(JSON)은 파일로 만들어 전송한다
curl -X POST http://localhost:10302/api/auth/login \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/login.json
```

받은 토큰을 다음 요청에 넣어 보고 3.3 의 흐름과 맞춰 본다. 액세스 토큰은 한 시간 뒤 만료된다(`expiresIn(3600L)`, AuthController 151줄).

> 계정이 잠겼으면 `UPDATE users SET loginFailCount=0, accountNonLocked=1 WHERE username='<username>';` 로 푼다. 컬럼 이름이 camelCase 인 점이 처음엔 낯설다.

---

## 5. [0단계] permission — 권한

이 모듈은 코드보다 DB 를 먼저 보는 쪽이 빠르다. 70개 파일이 있지만 엔티티 아홉 개가 전부이고, 나머지는 그 아홉을 읽고 쓰는 코드다.

| 엔티티 | 용도 |
|---|---|
| `DynamicRole` | 역할 (ROLE_ADMIN / ROLE_USER / ROLE_SUPERVISOR) |
| `UserDynamicRole` | 사용자 ↔ 역할 매핑 |
| `Permission` | 권한 정의 (메뉴 권한 + 기능 권한) |
| `PermissionType` / `FeatureType` | 권한·기능 분류 |
| `Menu` / `MenuType` | 메뉴 정의 |
| `MenuHelpStep` | 메뉴 도움말 |
| `PermissionAuditLog` | 권한 변경 감사 |

### 실습

```sql
SELECT * FROM dynamic_roles;
SELECT * FROM user_dynamic_roles WHERE user_id = (SELECT id FROM users WHERE username='<username>');
SELECT * FROM permissions LIMIT 20;
```

### 2026-10 기준으로 알아둘 것

7월과 가장 많이 달라진 자리가 여기다. 그때는 `@PreAuthorize("hasRole('ADMIN')")` 이 467건으로 1위였다. 지금은 1건이다. 1,495건이 `isAuthenticated()` 이고 110건쯤이 `hasFeature(...)` 다. 역할 문자열을 코드에 박지 않는다는 규칙(CRITICAL 19 · 27)이 그 사이에 저장소 전체를 지나갔다. 메뉴 노출은 BE 의 `menu-definition.json` 이 정하고, 메뉴마다 `PERM_{코드}_ACCESS` 권한 행이 자동으로 생긴다(CRITICAL 20). 자세한 구조는 다음 글, 인증·권한·메뉴 체계에서 다룬다.

### 함정

> 🔴 **`@PreAuthorize` 는 스위치가 켜져 있어야 동작한다.** `@EnableMethodSecurity(prePostEnabled = true)` 가 보안 설정 세 개와 `permission/config/PermissionSecurityConfig` 에 붙어 있다. 이게 빠지면 애너테이션은 에러 없이 무시된다.

> 🔴 **새 DB 는 `dynamic_roles` id 1/2/3 시드가 먼저다.** `aws-deploy/README.md` 는 `seed_dynamic_roles.sql` 을 먼저 실행하라고 하는데, 그 파일이 저장소에 없다(2026-10-12 확인). `V10.2__create_dynamic_roles_table.sql` 과 `mariadb/beforeEachMigrate__bootstrap_chat_execution_cancel_roles.sql` 이 관련 시드를 담고 있으니, 신규 DB 를 만들기 전에 빈 DB 로 Flyway 를 끝까지 돌려 보는 편이 안전하다.

---

## 6. [1단계] stt — 패턴 체득, 실질적 시작점

이 단계는 글 하나로 따로 뗐다. **[stt 모듈 — 모듈 구조 패턴 체득](/advisor/stt-module.html)** 글을 읽는다.

7월에 28개 파일이던 모듈이 지금은 65개다. 늘어난 37개는 대부분 통화의 계보를 기록하는 `lineage/` 와 발화를 외부 AI 로 보내도 되는지 판정하는 `policy/` 인데, 1단계에서는 둘 다 건너뛴다. 읽을 파일 여섯과 순서는 그대로다.

```
1) entity/STTEvent.java          통화 시작·종료 이벤트  (88줄)
2) entity/STTMessage.java        발화 문장             (202줄)
3) DB 확인                       stt_events / stt_messages
4) controller/STTController.java receiveSTTMessage (78~190줄) 만
5) service/STTService.java       saveSTTMessage (173~349줄) 만
6) ingest/SttIngestFilter.java   인입 필터 (183줄, 전부)
```

목표는 STT 를 아는 것이 아니다. 모듈 하나를 여는 순서를 몸에 붙이는 것이다. 여기를 지나면 나머지 60개 모듈에서 어디를 봐야 할지 먼저 보인다. 같은 크기대에 AI 자동 분류가 붙은 `counseltype`(35개)을 두 번째 표본으로 보면 "AI 호출이 붙으면 구조가 어떻게 달라지나"까지 보인다.

---

## 7. [2단계] evaluation — 핵심 업무 도메인

제품의 심장이다. 282개 파일이지만 여기만 제대로 알면 고객 문의의 대부분을 혼자 받을 수 있다.

### 테이블 5개 관계

```
evaluation_plan              평가 계획 (누구를·언제·몇 건)
      ↓
evaluation_target            평가 대상 (통화 1건 = 1행)
      ↓
evaluation_execution         평가 배치 실행 (1회 실행 = 1행)
      ↓
evaluation_result            채점 결과 (통화 1건 = 1행)

evaluation_schedule_config   계획별 실행 스케줄 (next_execution_at · lock)
```

### 읽는 순서

```
1) entity/EvaluationTarget.java       상태값(EvaluationStatus, 271줄) · 출처(SourceChannel) enum 포함
2) entity/EvaluationPlan.java         계획 설정 (대상 선택 방식 CONSULTANT / SCHEDULE)
3) DB SELECT 로 실제 데이터 확인
4) scheduler/EvaluationTargetCollectScheduler.java   (짧음) 대상 자동 수집
5) service/impl/EvaluationSchedulerServiceImpl.java  평가 실행 핵심 ← 길다, 아래 메서드만
      - checkAndExecuteSchedules()   (445줄) 실행 폴링 진입점
      - resolveScheduledTargets()    대상 선정 규칙 — 실제 구현은 EvaluationExecutionServiceImpl 251줄
```

### 상태 전이

```
PENDING → DATA_READY → IN_PROGRESS → COMPLETED
                            ↓
                   SKIPPED / FAILED / EXPIRED
```

평가 대상으로 뽑히는 건 `DATA_READY` 하나뿐이다. 이것만 기억해도 평가 문의의 절반은 풀린다.

### 대상 선택 방식

| 값 | 화면 표기 | 조회 조건 |
|---|---|---|
| `CONSULTANT` | 상담사 기준 | 계획에 할당된 상담사의 통화 |
| `SCHEDULE` | 연동 대상 기준 | 출처가 `EXTERNAL_SYNC` 인 통화 |

### 헷갈리기 쉬운 것 — 스케줄러가 여섯이다

평가 계획 화면에서 Cron 을 설정하면 여섯 개가 전부 그 시각에 맞춰 도는 줄 알기 쉽다. 그 Cron 을 보는 건 하나뿐이고 나머지 다섯은 하루 종일 자기 박자로 돈다. 2026-10-12 에 다시 확인했는데 주기는 7월과 같다.

| 스케줄러 | 주기 | 위치 | Cron 적용 |
|---|---|---|---|
| 평가 실행 폴링 (`checkAndExecuteSchedules`) | 60초 (`poll-interval-seconds`) | SchedulerServiceImpl 444줄 | 적용 |
| STT 자동 수집 (`EvaluationTargetCollectScheduler`) | 10분 (`collect.scheduler.interval-ms`) | scheduler/ | 상시 |
| 대상 자동 동기화 (`EvaluationTargetSyncScheduler`) | 1분 폴링 | scheduler/ 28줄 | 상시 |
| 중단 실행 정리 (`cleanupStaleExecutions`) | 15분 | SchedulerServiceImpl 168줄 | 상시 |
| 만료 락 해제 | 5분 | SchedulerServiceImpl 922줄 | 상시 |
| 로그 보관 정리 | 매일 03:00 | SyncScheduler 42줄 | 상시 |

> 🔴 **실행 판정은 "지금이 Cron 시각인가"가 아니다.** "`next_execution_at` 이 현재를 지났는가"다. 이 값은 배치가 정상 종료한 뒤에만 갱신되기 때문에, 서버가 배치 도중 죽으면 재기동 후 시간대와 무관하게 한 번 더 돈다. "설정한 시간 외에 평가가 돌았다"는 문의가 오면 먼저 여기를 본다.

### 진단 쿼리

```sql
SELECT id, plan_id, cron_expression, last_executed_at, next_execution_at,
       lock_owner, lock_expire_at, NOW() AS now
FROM evaluation_schedule_config;
```

---

## 8. [3~6단계] 개요

여기부터는 모듈마다 한 문단씩만 적는다. 필요해지기 전에 더 읽어 둘 이유가 없고, 읽어 둬도 그때까지 남아 있지 않는다.

### 3단계 — `recording` (112) → `sttanalytics` (153)

통화가 밖에서 어떻게 들어와 분석되는지. `recording` 의 중심은 고객사 DB 의 뷰 테이블을 읽어 오는 수집기들이고, `recording/collector/impl/` 에 Oracle, MariaDB, API, FTP, SFTP, SCP, Local 일곱 종류가 나란히 있다.

### 4단계 — `ai` (1,227) — 전부 보지 말 것

세 서브패키지만 본다. 이 셋을 알아야 다른 모듈의 AI 호출부가 읽힌다.

| 패키지 | 내용 |
|---|---|
| `ai/execution/` | AI 호출 실행 |
| `ai/prompt/` | 프롬프트 관리 |
| `ai/execution/routing/` | 모델 선택·폴백 (정책·후보 순서·시도 이력). `ai/routing/` 은 채팅용 Smart Routing 넷뿐이고 기본 꺼져 있다 (2026-10-12 정정) |

### 5단계 — `rag` (274) → `kms` (774)

벡터 검색(PostgreSQL pgvector)과 지식베이스.

### 6단계 — `orchestration` (515) → `agi` (713)

워크플로우 빌더와 자율 에이전트. 가장 어렵고 가장 자주 바뀐다. 손대기 전에 `claudedocs/agi/AGI_TOOL_ENHANCEMENT_ANALYSIS.md` 와 `claudedocs/orchestration/README.md` 를 먼저 읽는다.

---

## 9. 자주 쓰는 명령어

### 백엔드

```bash
./gradlew bootRun -Pprofile=local        # 로컬 기동 (Kafka off, 가장 빠름)
./gradlew compileJava -q                 # 컴파일만 (수정 후 즉시)
bash scripts/ci/test-chunked.sh          # 회귀 테스트 — 묶음 순차 (전체 일괄 ./gradlew test 금지, CRITICAL 23)
./gradlew test --tests "ClassName"       # 단일 테스트
./gradlew bootJar                        # 배포용 JAR
```

> 로컬 BE 가 떠 있는 동안 다른 gradle 태스크를 돌리면 BE 가 죽는다. 라이브 검증 중에는 컴파일도 미룬다.

### 프론트엔드 (React 단일 트랙, Vue `stt-client/` 는 삭제됐다)

```bash
cd web-react
npm run dev          # 로컬 (vite 8090 → BE 10302 프록시)
npm run build:check  # tsc -b + vite build 전체 검증
npm test             # vitest (순차, CRITICAL 24)
```

### 포트

| 환경 | BE | FE |
|---|---|---|
| local | 10302 | 8090 (vite dev) |
| dev | 10303 | 8081 |
| dev-test | 10304 | 8083 |

기타: MariaDB 3306/3307 · PostgreSQL 5432/5434 · MongoDB 27017 · Redis 6379 · Kafka 9092

---

## 10. 지뢰밭 — 모르고 밟으면 장애

전체 목록은 `AGENTS.md` 의 CRITICAL 인덱스 28개와 `CODE_REVIEW_CHECKLIST.md` 에 있다. 아래는 초반에 유난히 자주 밟는 것만 추렸다. 번호는 CRITICAL 번호다.

| # | 내용 |
|---|---|
| 1 | Flyway DDL 은 전부 `IF NOT EXISTS` / `IF EXISTS` |
| 2 | Entity 변경 시 같은 PR 에 Flyway 마이그레이션 |
| 3 | 외부 호출은 `@CircuitBreaker` + null-safe fallback |
| 6 | 중첩 `@Transactional(REQUIRES_NEW)` 금지 → 이벤트 기반으로 분리 |
| 7 | 모든 `@Transactional` 에 `timeout` 명시 (기본 10초) |
| 8 | `readOnly` 트랜잭션 안에서 LLM·외부 I/O 호출 금지 |
| 11 | LLM 호출에 `@Retry` 금지 (`@CircuitBreaker` 만) |
| 12 | `@TransactionalEventListener(AFTER_COMMIT)` 는 self-call 금지 (AOP 우회) |
| 19 | API 인가는 인증 여부로만 — role 하드코딩 금지 |
| 20 | 메뉴는 BE `menu-definition.json` 이 SSOT — FE 는 레지스트리만 |
| 28 | 운영 DB 직접 조작 금지 — Flyway + 배포 파이프라인으로만 |
| — | Virtual Thread 활성 상태 → `synchronized` 안에서 I/O 금지 (pinning) |
| — | FK 멱등 추가에 `ADD CONSTRAINT IF NOT EXISTS FOREIGN KEY` 금지 (MariaDB 미지원) |
| — | 데이터 INSERT 마이그레이션은 `created_at` / `updated_at` 값을 `NOW()` 로 명시 |

---

## 11. 최종 자가진단

구조, 인증·권한, 데이터, 업무 도메인 순서다. 막히는 문항이 있으면 그 절로 돌아간다.

1. 새 기능의 REST API 를 추가하려면 어떤 디렉토리에 무슨 파일을 만드나?
2. 임의의 모듈에서 "이 API 가 뭘 하는지" 5분 안에 찾아갈 수 있나?
3. 특정 URL 이 인증 없이 열려 있는지 어디서 확인하나?
4. 403 이 떴을 때 확인 순서는?
5. Entity 를 수정했다. 그다음 반드시 해야 할 일은?
6. 새 모듈의 Repository 빈을 못 찾는다면 어디를 보나?
7. 평가 대상이 `DATA_READY` 가 아니면 어떻게 되나?
8. 설정한 Cron 시간이 아닌데 평가가 돌았다. 어디를 확인하나?

---

*문서 끝*
