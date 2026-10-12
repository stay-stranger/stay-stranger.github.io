# 인증 · 권한 · 메뉴 체계

> 어드바이저 백엔드/프론트엔드의 인증·인가·메뉴 구조
> 최초 작성 2026-07-27 · 전수 재측정 2026-10-12 (커밋 `f06317ca47`)

> 📌 **갱신 요지** 7월 초판과 가장 크게 달라진 세 가지. `hasRole('ADMIN')` 467건이 1건이 됐고(CRITICAL 19 · 27), 메뉴의 원본이 BE `menu-definition.json` 으로 넘어가 FE 는 레지스트리만 갖게 됐으며(CRITICAL 20) 둘을 잇는 열쇠는 code 가 아니라 path 다. Vue 트랙은 삭제돼서 7절의 Vue 비교는 통째로 뺐다.

---

## 1. 전체 그림

요청 하나가 컨트롤러에 닿기까지 문을 셋 지난다. 성 하나에 문이 셋 있는 셈인데, 셋이 묻는 질문이 전부 다르다.

```
HTTP 요청
   │
   ▼
[필터] JwtAuthenticationFilter          "너 누구야?"  → 신원을 SecurityContext 에 채움
   │                                     ※ 여기서 차단하지 않는다
   ▼
[1차] SecurityConfig URL 매트릭스        "이 URL 호출해도 되나?"  → 실패 시 401/403
   │                                     ※ 컨트롤러 코드에 도달조차 못 함
   ▼
[2차] @PreAuthorize                      "이 기능 써도 되나?"     → 실패 시 403
   │
   ▼
[3차] 서비스 코드 (범위 제한)             "누구의 데이터까지?"     → 본인 것만 등
   │
   ▼
컨트롤러 / 서비스 본문
```

| 축 | 질문 | 판정 위치 |
|---|---|---|
| 인증 | 누구인가 | `JwtAuthenticationFilter` |
| 행위(Action) | 무엇을 할 수 있나 | `@PreAuthorize` — 지금은 거의 전부 `isAuthenticated()`, 파괴적 행위만 `hasFeature()` |
| 범위(Scope) | 누구의 데이터에 | 서비스/쿼리 코드 |

> ⚠️ **`@PreAuthorize` 는 범위를 말할 줄 모른다.** "수정할 수 있다"까지는 말해도 "자기 것만 수정할 수 있다"는 못 한다. 범위는 언제나 코드가 맡는다. 이 문장을 모르면 뒤의 8절이 전부 이상하게 읽힌다.

---

## 2. 인증 — JwtAuthenticationFilter

`core/security/JwtAuthenticationFilter.java`, 343줄. 모든 요청이 이 파일을 지나간다. 7월에는 102줄이었는데 그 사이 계정이 삭제되거나 영구 정지된 경우를 토큰 만료와 따로 다루는 판정이 들어왔고, ASYNC 디스패치에서 `SecurityContext` 를 정리하는 코드(94·119·233줄)가 붙었다. 뼈대는 그대로다.

```
① 토큰 추출 (resolveToken, 322줄)
     1순위: Authorization: Bearer <토큰>
     2순위: ?token=<토큰>                                   (331줄)
            단, URL 에 /stream 또는 /sse 포함 시에만 허용      (335줄)
            (EventSource API 가 커스텀 헤더를 못 보내기 때문)

② tokenProvider.validateToken(token)                       (129줄)

③ 통과 시 userDetailsService.loadUserByUsername() 으로 DB 에서 User 로드   (135줄)
     → SecurityContextHolder 에 인증 정보 저장

④ 사용자 로드 실패(삭제·영구 정지) → SecurityContext 를 비워 미인증 처리
     ※ 토큰 만료와 계정 회수를 구분한다 (126줄 주석) — 복원은 만료에만 허용

⑤ 토큰이 없거나 틀려도 여기서 막지 않는다 → filterChain.doFilter() 로 통과
```

> 🔑 **⑤가 이 파일의 성격이다.** 필터는 문지기가 아니라 명부를 든 안내인이다. 이름을 확인해 적어 둘 뿐이고, 들여보낼지는 뒤에 선 문이 정한다. 그 문이 URL 매트릭스다.

### 401 과 403

| 응답 | 의미 | 원인 |
|---|---|---|
| 401 Unauthorized | 신원 자체가 없음 | 토큰 미첨부 / 만료 / 위조 → SecurityContext 가 비어 있음 |
| 403 Forbidden | 신원은 있으나 권한 부족 | 로그인은 했지만 기능 권한 미달 |

401 이면 토큰 문제이고 403 이면 권한 문제다. 토큰을 분명히 보냈는데 401 이 온다면 대개 만료됐거나 `Bearer ` 접두사가 빠진 것이다.

---

## 3. 1차 관문 — URL 매트릭스 (SecurityConfig)

### 프로파일별로 파일이 셋이다

| 파일 | 줄 수 | 적용 프로파일 (`@Profile`) |
|---|---|---|
| `core/config/LocalSecurityConfig.java` | 391 | `local`, `test`, `dev-test` |
| `core/config/DevSecurityConfig.java` | 304 | `dev` |
| `core/config/SecurityConfig.java` | 398 | `prod`, `naver` |

자기 프로파일 것 하나만 본다. 아래 줄 번호는 전부 `LocalSecurityConfig` 기준이다.

> 📌 이 파일 41줄의 클래스 주석에는 "JWT 인증 없이 기본 인증만 제공"이라고 적혀 있다. 사실이 아니다. 108·111줄에서 JWT 필터를 만들고 362줄에서 체인에 붙인다. 주석이 코드보다 먼저 늙었다.

> 📌 239줄 주석에 따르면 운영 환경이 local 프로파일로 구동된 이력이 있다. 이름만 Local 이지 운영에서도 돈다.

### 핵심 개념 ① — 순서가 곧 로직 (first match wins)

규칙은 위에서 아래로 읽히고, 처음 맞는 규칙 하나만 적용된다.

```java
.requestMatchers(HttpMethod.POST, "/api/stt/message").permitAll()   // 177줄
.requestMatchers(HttpMethod.POST, "/api/stt/event").permitAll()     // 178줄
.requestMatchers("/api/stt/**").authenticated()                     // 179줄
```

`POST /api/stt/message` 는 177줄에서 걸려 인증 없이 들어가고, `GET /api/stt/events` 는 179줄에서 걸려 로그인을 요구받는다. 순서를 뒤집으면 179줄이 전부를 먼저 삼켜서 177줄은 영원히 차례가 오지 않는다. 좁은 규칙이 위, 넓은 규칙이 아래. 182·184줄의 actuator 도 같은 모양이다.

```java
.requestMatchers("/actuator/health", "/actuator/health/**", "/actuator/info", "/actuator/prometheus").permitAll()  // 좁게 열고
.requestMatchers("/actuator/**").hasRole("ADMIN")                                                                   // 나머지 잠금
```

### 핵심 개념 ② — 종결어

| 종결어 | 요구 조건 | 통과 대상 | 2026-10 사용 현황 |
|---|---|---|---|
| `permitAll()` | 없음 | 누구나 (비로그인 포함) | 열어야 할 경로만 |
| `authenticated()` | 로그인 | 로그인한 전원 | 대부분 |
| `hasRole('ADMIN')` | 특정 역할 | 관리자만 | `/actuator/**` 한 곳 (Local 1 · Dev 1 · 운영 8건) |

API 경로에 `hasRole` 을 새로 쓰지 않는다. 인가는 인증 여부로만 하고, 세부 권한은 2차 관문의 `hasFeature` 와 서비스 범위로 내린다(CRITICAL 19).

### 핵심 개념 ③ — 기본은 잠금

```java
.anyRequest().authenticated()   // 357줄 — 마지막 그물
```

위에서 안 걸린 요청은 전부 로그인을 요구받는다. 새 API 를 만들면 아무 설정 없이도 보호되고, 열고 싶을 때만 위에 한 줄을 더한다. 문은 기본으로 닫혀 있다.

### 핵심 개념 ④ — `permitAll` ≠ 무방비

`permitAll` 목록만 보면 성벽에 구멍이 숭숭 뚫린 것 같다. 대부분은 다른 사람이 지키고 있다.

| 경로 | 줄 | Spring Security | 실제 방어 |
|---|---|---|---|
| `/api/v1/chat/**` | 324 | permitAll | VoiceApiKeyFilter (API Key) |
| `POST /api/agent/register` | 228 | permitAll | AgentApiKeyFilter (API Key) |
| `/ws-ssh` | 187 | permitAll | 핸들러가 쿼리파라미터 JWT 직접 검증 |
| `POST /api/orchestration/webhooks/*/trigger` | 307 | permitAll | HMAC 서명 |
| `POST /api/kms/slack/**` | 248 | permitAll | HMAC 서명 |

`permitAll` 은 "Spring Security 단계는 통과시키고 인증은 다른 곳에서 한다"는 뜻이다. 7월 표에 있던 `/api/artifact/pptx/*/callback` 은 세 설정 어디에도 남아 있지 않아 지웠다.

### 핵심 개념 ⑤ — 왜 열어야 하는가

1. 로그인 전이라 토큰이 없다 — `/api/auth/**` (144줄)
2. 브라우저가 헤더를 못 붙인다 — `<img src>` 아바타, `<audio>` 녹취 스트리밍, `iframe` embed, `EventSource` SSE. 가장 흔한 이유다
3. 내부 시스템 통신 — Bridge 소프트폰, ACS 릴레이
4. 외부 시스템 콜백 — 웹훅, Slack
5. 정적 자원 — `/react/**`, `/assets/**`

### 필터 등록 (362~384줄)

```
362  addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter)   JWT 검증 → SecurityContext 채움
363  addFilterAfter(ragStopwordServiceAuthenticationFilter, JwtAuthenticationFilter)   (조건부)
372  addFilterAfter(embedAuthTokenFilter, JwtAuthenticationFilter)                     임베드 토큰 (조건부)
378  addFilterBefore(voiceApiKeyFilter, UsernamePasswordAuthenticationFilter)          API Key (/api/v1/chat/**)
384  addFilterBefore(virtualKeyGatewayAuthFilter, UsernamePasswordAuthenticationFilter) vkey 토큰 (조건부)
      ↓
     URL 매트릭스 검사   ★ 실제 차단은 여기
      ↓
     컨트롤러
```

> 여러 필터가 같은 기준점(`UsernamePasswordAuthenticationFilter` 앞)에 걸려 있어서, 실제 실행 순서는 기동 로그의 `DefaultSecurityFilterChain` 출력으로 확인해야 한다. 7월 문서에 적었던 "Voice → VKey → JWT → Embed" 순서는 실측이 아니었다. 이번에 그 줄을 지웠다.

---

## 4. 로그인 흐름

`SecurityConfig` 는 토큰을 만들지 않는다. 그런데 로그인 요청은 분명 이 설정을 지나간다. 두 가지 일만 한다.

```
POST /api/auth/login  { username, password }
   │
   ▼
[1] URL 매트릭스 144줄  .requestMatchers("/api/auth/**").permitAll()
        → 통과. 토큰 없어도 안 막음                        ★ 역할 1
   │
   ▼
[2] JwtAuthenticationFilter
        토큰이 없으니 아무것도 안 하고 통과 (발급 전이므로 당연)
   │
   ▼
[3] AuthController.login()  (110줄)                        ← 실제 처리
        ├─ authenticationManager.authenticate(...)   ID/PW 검증
        │     ↑ 이 빈을 SecurityConfig 가 제공         ★ 역할 2
        │       (AuthenticationManager → DaoAuthenticationProvider
        │        → BCryptPasswordEncoder 로 비번 대조)
        │
        ├─ jwtTokenProvider.createAccessToken(...)   ← 토큰 생성은 여기
        ├─ jwtTokenProvider.createRefreshToken(...)
        │
        └─ 응답 { accessToken, refreshToken, expiresIn: 3600, roles, ... }   (151줄)
```

| 질문 | 답 |
|---|---|
| 로그인 요청이 SecurityConfig 를 타나? | 예 — `permitAll` 로 통과 |
| SecurityConfig 가 ID/PW 를 검증하나? | 간접적 — 검증용 빈 3개를 제공 |
| SecurityConfig 가 JWT 를 만드나? | 아니오 — `JwtTokenProvider` 가 만듦 |
| JwtAuthenticationFilter 가 관여하나? | 아니오 — 검증할 토큰이 아직 없음 |

JWT 필터의 무대는 두 번째 요청부터다. 첫 요청에서 안내인은 빈 명부를 들고 서 있을 뿐이다.

액세스 토큰은 한 시간 뒤 만료되고 `POST /api/auth/refresh` (433줄)로 갱신한다. 로그인에 성공하면 `user.handleLoginSuccess(clientIp)` (137줄)가 실패 카운터를 0으로 돌린다. 계정이 잠겼을 때 손으로 푸는 쿼리는 `UPDATE users SET loginFailCount=0, accountNonLocked=1 WHERE username='<username>';` 이고, 컬럼이 camelCase 라는 점만 기억하면 된다.

---

## 5. 2차 관문 — @PreAuthorize

403개 파일에서 쓴다. 표현식을 세어 보면 아래와 같다 (2026-10-12).

| 사용 횟수 | 표현식 |
|---|---|
| 1,495 | `isAuthenticated()` |
| 83 | `hasFeature('도메인:자원:행위')` |
| 24 | `hasFeature(...) and hasFeature(...)` |
| 20 | `permitAll()` |
| 1 · 1 | `hasAnyFeature(...)` · `hasAllFeatures(...)` |
| 1 | `hasMenuPermission('admin')` |
| 1 | `hasRole('ADMIN')` |

7월에 이 표를 처음 만들었을 때 1위는 `hasRole('ADMIN')` 467건이었고, `hasRole('ADMIN') or hasMenuPermission(...)` 패턴이 33건 있었다. 석 달 뒤 다시 세었더니 한 건이 남아 있었다. 그 사이에 "API 인가는 인증 여부로만, role 하드코딩 금지"(CRITICAL 19)와 "role 판정을 기능 권한으로 옮길 때는 같은 범위 · 관리자 단축 없음 · 호출부 전수"(CRITICAL 27)가 저장소 전체를 한 번 지나간 것이다.

### `isAuthenticated()` 의 뜻

로그인만 되어 있으면 통과. 역할도 권한도 보지 않고, `JwtAuthenticationFilter` 가 명부에 이름을 적었는지만 본다. 이것이 기본값이 된 이유는 간단하다. 누가 무엇을 볼 수 있는지는 메뉴 매트릭스(DB)와 서비스의 범위 판정이 정하기 때문에, 컨트롤러는 "로그인했나"만 물으면 된다. 다만 `permitAll()` 로 내려가서는 안 된다. 그러면 "본인"이 누구인지 알 길이 없어진다.

### 커스텀 함수 (Spring 표준 아님)

정의는 `permission/security/CustomMethodSecurityExpressionRoot.java` 에 있다.

| 함수 | 줄 | 용도 | 판정 근거 |
|---|---|---|---|
| `hasFeature(코드)` | 65 | 기능 권한 | DB 조회 (캐시) |
| `hasAnyFeature(...)` / `hasAllFeatures(...)` | 118 / 138 | 복수 검사 | DB 조회 |
| `hasMenuPermission(코드)` | 47 | 메뉴 접근 | DB 조회 — 지금은 코드에서 한 곳만 쓴다 |

### 기능 권한 코드의 모양

```
consultation:history:view:all      전체 열람
consultation:history:view:own      본인 열람
consultation:history:delete:all    전체 삭제    ← 누구에게 줄지가 DB 데이터
counsel-type:reclassify:apply      재분류 적용
```

`도메인:자원:행위[:범위]`. 범위까지 코드에 넣어 두면 `ADMIN` 이나 `SUPERVISOR` 같은 역할 이름이 소스에서 사라진다. 요구사항이 바뀌면 역할과 권한을 잇는 DB 행만 고치면 되고, 배포는 필요 없다.

### 선택 기준

| 상황 | 방식 |
|---|---|
| 조회·일반 행위 | `isAuthenticated()` + 서비스에서 범위 |
| 삭제·승인·적용처럼 되돌리기 어려운 행위 | `hasFeature('…')` |
| 메뉴 진입 가부 | 컨트롤러가 아니라 메뉴 매트릭스 (7절) |

역할로 막고 싶어지는 순간이 온다. 그때 "여섯 달 뒤 고객이 이걸 바꿔 달라고 할까"를 물어보면 거의 언제나 '예'다. 그러면 기능 권한이다.

---

## 6. 권한 데이터 구조

### 테이블 사슬

```
users
  └─ user_dynamic_roles          누가 어떤 역할인지
       └─ dynamic_roles          역할 (ROLE_ADMIN / ROLE_USER / ROLE_SUPERVISOR)
            │                     · parentRole → 역할 상속
            │                     · priority   → 우선순위
            └─ role_permissions  역할이 가진 권한
                 └─ permissions
                      ├─ permission_type = MENU  → menu_id 로 menus 연결  (메뉴마다 PERM_{코드}_ACCESS 자동 생성)
                      └─ permission_type = 그 외  → 기능 권한 (hasFeature)
                           └─ menus              실제 메뉴. menu-definition.json 에서 기동 시 동기화
```

> 🔑 **서랍은 하나, 칸은 둘.** `permissions` 테이블 하나에 `permission_type` 으로 칸만 나뉘어 있을 뿐이다. 이걸 모르면 "메뉴 권한은 어느 테이블이냐"를 한참 찾게 된다.

### 권한 판정 코드 — `DynamicPermissionServiceImpl`

```java
// DynamicPermissionServiceImpl.java
@Cacheable(value = "userPermissions", key = "#username", cacheManager = "permissionCacheManager")   // 44줄
public Set<String> getUserPermissions(String username) { ... }                                     // ① 전체 권한 코드

@Cacheable(value = "userMenus", key = "#username", cacheManager = "permissionCacheManager")         // 78줄
public Set<String> getUserMenuCodes(String username) { ... }                                       // ② MENU 타입만 → 메뉴 code

public boolean hasMenuAccess(String username, String menuCode) {                                   // 141줄
    Set<String> menuCodes = getUserMenuCodes(username);
    return menuCodes.contains(menuCode);                                                           // 단순 포함 검사
}

@CacheEvict(value = {"userPermissions", "userMenus"}, ...)                                         // 172 · 181줄
```

`hasFeature` 는 ①의 집합에 코드가 있는지, `hasMenuPermission` 은 ②의 집합에 있는지 본다. 둘 다 사용자별 캐시를 탄다. 캐시는 기억이고, 기억은 DB 를 직접 고쳐도 저절로 바뀌지 않는다. 9절의 첫 번째 함정이 여기서 나온다.

### 확인 SQL

```sql
-- 역할 목록
SELECT id, code, name, is_active, priority FROM dynamic_roles;

-- 특정 사용자의 역할
SELECT r.code, r.name FROM dynamic_roles r
JOIN user_dynamic_roles ur ON ur.role_id = r.id
JOIN users u ON u.id = ur.user_id
WHERE u.username = '<username>';

-- 접근 가능 메뉴 코드 = 사이드바에 보이는 메뉴
SELECT DISTINCT m.code, m.name
FROM users u
JOIN user_dynamic_roles ur ON ur.user_id = u.id
JOIN dynamic_roles r       ON r.id = ur.role_id
JOIN role_permissions rp   ON rp.role_id = r.id
JOIN permissions p         ON p.id = rp.permission_id
JOIN menus m               ON m.id = p.menu_id
WHERE u.username = '<username>'
  AND p.permission_type = 'MENU'
  AND p.is_active = 1;

-- 기능 권한 코드 (hasFeature 인자로 쓰이는 값)
SELECT code, name, permission_type, feature_type FROM permissions
WHERE permission_type <> 'MENU' LIMIT 20;
```

---

## 7. 메뉴 체계

### 역할 분담 (CRITICAL 20, 2026-08-05 확정)

```
BE  src/main/resources/menu/menu-definition.json   "어떤 메뉴가 존재하고, 어떤 code·path·순서·노출인가"   [SSOT]
BE  menus + permissions 테이블                      "이 사람에게 보일 것인가"                              [DB, 기동 시 JSON 과 동기화]
FE  web-react/src/config/menu.ts                    "그 path 를 어느 컴포넌트가 그리나"                      [구현 레지스트리]
```

| | 실측 (2026-10-12) |
|---|---|
| `menu-definition.json` | 2,422줄 · 노드 230개 · 최상위 25개 · 노드 키 `code icon name order path requiresAuth titleKey type visible` |
| `menu.ts` | 1,595줄 · `code:` 92개 · `lazy:` 221개 |
| React 페이지 | 205개 (`*Page.tsx`) |

무엇을 보여줄지(존재·계층·순서·라벨·노출)는 BE 가 정하고, FE 는 그 path 를 어떻게 그릴지만 안다. 7월 문서에 "FE 하드코딩은 불가피하다"고 썼는데 절반만 맞았다. `lazy: () => import(...)` 와 아이콘은 여전히 FE 에 있어야 한다. 번들러가 빌드 시점에 import 를 읽어야 코드 스플리팅이 되기 때문이다. 하지만 label 과 order 와 계층과 permission 은 FE 에서 빠졌다.

### FE 가 메뉴를 받는 길

```
로그인
  → useMyMenus()  (hooks/use-my-menus.ts 38줄)
  → GET /api/permissions/menus        역할에 부여된 메뉴 권한으로 필터된 트리
  → lib/menu-merge.ts                  BE 노드 ↔ menu.ts 레지스트리를 path 로 매칭 (byPath, 45~65줄)
  → Sidebar.tsx (148줄) · HomePage · CommandPalette 렌더
  → 라우트 진입은 allowedPaths 로 판정
```

매칭은 path 기준이라 code 접두사가 달라도(`MENU_BILLING_DASHBOARD` 와 `BILLING_DASHBOARD`) 아무 일도 생기지 않는다. 대응 화면이 없는 BE 메뉴는 `unresolved` 로 표시되고, 메뉴 관리 화면(`MenuManagementPage`, `MenuAlignmentSummary`)에서 그 목록을 볼 수 있다. 사이드바의 서브탭은 `usePermission(sub.permission)` (Sidebar 777줄)로 한 줄씩 기능 권한을 확인한다. `App.tsx` 에 등록된 `<Route>` 는 로그인과 공유 링크, 공개 페이지 같은 18개뿐이고, 로그인 뒤의 URL 은 `WorkspaceShell` 이 받아 `MENU_TREE` 에서 찾는다. 멀티탭 UI 때문에 그렇게 됐다.

### path 가 접착제다

```
menu-definition.json 의  path: '/agent/dashboard'
        ↕  반드시 일치
menu.ts 의              path: '/agent/dashboard'  (+ icon, lazy)
```

두 곳의 path 가 어긋나면 에러 한 줄 없이 메뉴가 사라지거나 `unresolved` 로 남는다. 7월 문서는 "code 가 세 곳에서 일치해야 한다"고 썼다. 지금 FE 의 `code:` 는 대부분 메뉴 code 체계와 다른 값(서브탭이나 라우트 키)이라 code 교집합은 17개뿐이다. 신경 쓸 것은 path 하나다.

### 신규 메뉴 추가 절차

| # | 위치 | 배포 필요 |
|---|---|---|
| 1 | `menu-definition.json` 에 노드 추가 (code · path · order · visible) | BE 재기동 |
| 2 | `menu.ts` 에 같은 path 로 `icon` / `lazy` 등록 + 페이지 컴포넌트 | FE 빌드 |
| 3 | BE 기동 → `menus` 테이블 동기화 + `PERM_{코드}_ACCESS` 자동 생성 | — |
| 4 | 권한 매트릭스 화면에서 역할별 부여 | 불필요 (DB) |

한쪽만 하면 CI 가드가 막는다. 컨트롤러에는 `@PreAuthorize("isAuthenticated()")` 만 둔다. 메뉴 권한을 컨트롤러에서 또 검사하지 않는다. 새 메뉴를 만드는 데는 배포가 필요하고 기존 메뉴의 권한을 조정하는 데는 DB 만 있으면 된다는 점은 7월과 같다. 고객이 "이 역할에게 이 메뉴 보여 주세요"라고 하면 배포 없이 끝난다.

### 고객사별 커스터마이징

| 요청 | 대응 | 배포 |
|---|---|---|
| 메뉴 이름 변경 | JSON `name` / `titleKey` | BE 재기동 |
| 메뉴 순서 변경 | JSON `order` | BE 재기동 |
| 가시성 변경 | 권한 매트릭스 (또는 JSON `visible`) | 불필요 |
| 새 메뉴 | JSON + `menu.ts` + 컴포넌트 | BE·FE 모두 |

> ❓ **미확인** FE 가 `titleKey` 를 어느 i18n 리소스에서 번역하는지는 이번에 찾지 못했다. `name` 이 폴백이라는 것은 JSON 구조로 보아 분명하다.

---

## 8. 권한 설계 규칙 (실무)

### 3줄 규칙

```
1. 메뉴 진입   → 컨트롤러는 @PreAuthorize("isAuthenticated()") 만. 노출은 메뉴 매트릭스(DB)가 정한다
                 [대부분 여기서 끝난다]

2. 본인 것만   → /my + isAuthenticated() + 서버가 토큰에서 userId 추출
                 [드물다. 현재 전체 11곳]

3. 파괴적 행위 → hasFeature('도메인:자원:행위:범위') 로 개별 명시
                 [삭제·승인·적용. 요구사항이 갈리는 지점은 거의 언제나 여기다]
```

### `/my` 패턴

"내가 만든 것, 나에게 배정된 것"을 조회할 때 쓴다.

```java
@GetMapping("/my")
@PreAuthorize("isAuthenticated()")          // 메뉴 권한 요구 안 함
public Page<EvaluationResultDTO> getMine(Pageable pageable) {
    Long userId = SecurityUtils.getCurrentUserIdOrThrow();   // ★ 토큰에서 추출
    MyIdentity identity = statisticsService.resolveMyIdentity(userId);
    if (identity.isEmpty()) return Page.empty(pageable);      // 매핑 없으면 빈 결과

    return evaluationQueryService.findResults(
        EvaluationResultSearchCriteria.builder()
            .ownerConsultantId(identity.consultantId())        // ★ 본인으로 고정
            .build(), pageable);
}
```

이 패턴은 권한을 낮추는 것이 아니라 범위를 좁히는 것이다. 요구하는 건 로그인뿐이지만 범위는 서버가 못박는다. 신원은 클라이언트가 정하지 못한다. `consultantId` 파라미터를 받지 않는다는 것이 그 뜻이다. 매핑이 없으면 예외가 아니라 빈 페이지를 돌려준다.

### 현재 존재하는 `/my` 전수 (11개, 2026-10-12)

| 모듈 | 엔드포인트 |
|---|---|
| evaluation | `/my`, `/my/statistics`, `/my/{id}/details`, `/my/{id}/ai-coaching`(GET/POST) |
| orchestration | `/my`, `/my/count` (결재 승인함) |
| feedback | `/my` |
| agi | `/my-traces` |
| assist | `/my/stats` |
| permission | `/my-menus` (사이드바용) |

7월에는 14개였는데 kms 의 셋이 빠져 11개가 됐다. 61개 모듈 중 여섯에만 있다. 패턴이 "내가 만든 것"과 "나에게 배정된 것" 둘뿐이라 많아질 수가 없다. `/my-menus` 가 `isAuthenticated()` 인 것도 같은 이유다. 로그인만 하면 누구나 사이드바를 그려야 한다.

### Case 1 — 관리자 메뉴 + 본인 대시보드

요구는 이렇다. 평가결과 관리 메뉴는 관리자만 쓰되, 일반 사용자도 대시보드에서 자기 평가결과는 봐야 한다. 엔드포인트를 둘로 나눈다. 둘 다 컨트롤러는 `isAuthenticated()` 다.

| 용도 | 엔드포인트 | `@PreAuthorize` | 범위 |
|---|---|---|---|
| 관리 (전체) | `GET /api/evaluation-results` | `EVALUATION_VIEW_ALL` = `"isAuthenticated()"` (85줄) | 메뉴 노출은 매트릭스, 범위는 서비스 |
| 대시보드 (본인) | `GET /api/evaluation-results/my` | `isAuthenticated()` | 서버가 본인으로 강제 |

7월에는 관리 쪽이 `hasRole('ADMIN') or hasMenuPermission('MENU_EVALUATION_RESULTS')` 였다. 지금은 컨트롤러가 메뉴 권한을 보지 않고 매트릭스가 사이드바 노출로 통제한다. 일반 사용자에게 관리 메뉴 권한을 주면 사이드바에 관리 메뉴가 떠 버리니까 `/my` 로 나누는 게 맞다는 결론은 그대로다.

### Case 2 — 3단계 역할 × 범위 × 행위

| | 열람 | 수정 | 삭제 |
|---|---|---|---|
| 관리자 | 전체 | 전체 | 전체 |
| 중간관리자 | 전체 | 전체 | 불가 |
| 일반사용자 | 본인만 | 본인만 | 본인만 |

```java
@PreAuthorize("hasRole('ADMIN')")              // ❌ 일반사용자가 본인 것을 못 지움 + CRITICAL 19 위반
@PreAuthorize("hasAnyRole('ADMIN','USER')")    // ❌ 일반사용자에게 전체 삭제가 열림
```

삭제할 수 있는지는 역할이 아니라 "권한과 소유의 조합"이 정한다. 역할 하나로는 표현이 안 된다. 그래서 게이트는 느슨하게 두고 판정은 서비스에서 한다.

```java
// 1. 컨트롤러 — 클래스 레벨은 로그인만
@RestController
@RequestMapping("/api/consultation-history")
@PreAuthorize("isAuthenticated()")
public class ConsultationHistoryController { ... }

// 2. 범위 결정자 — 권한 코드 기반 (배포 없이 조정 가능)
public record AccessScope(boolean viewAll, boolean updateAll, boolean deleteAll, Long userId) {
    public static AccessScope resolve(DynamicPermissionService svc) {
        String username = SecurityUtils.getCurrentUsername();
        Long userId = SecurityUtils.getCurrentUserIdOrThrow();
        return new AccessScope(
            svc.hasPermission(username, "consultation:history:view:all"),
            svc.hasPermission(username, "consultation:history:update:all"),
            svc.hasPermission(username, "consultation:history:delete:all"),
            userId);
    }
}

// 3. 조회 — 범위를 쿼리에 강제 주입 (클라이언트 값 무시)
@GetMapping
public Page<HistoryDTO> list(HistorySearchCriteria criteria, Pageable pageable) {
    AccessScope scope = AccessScope.resolve(permissionService);
    if (!scope.viewAll()) criteria.setOwnerId(scope.userId());   // ★ 덮어쓰기
    return historyService.search(criteria, pageable);
}

// 4. 삭제 — 소유권 + 권한 조합
@DeleteMapping("/{id}")
@PreAuthorize("hasAnyFeature('consultation:history:delete:own','consultation:history:delete:all')")
public void delete(@PathVariable Long id) {
    History target = historyService.findById(id);
    AccessScope scope = AccessScope.resolve(permissionService);
    if (!scope.deleteAll() && !target.getOwnerId().equals(scope.userId())) {
        throw new PermissionDeniedException("삭제 권한이 없습니다");
    }
    historyService.delete(id);
}
```

범위를 권한 코드에 넣으면 역할 이름이 코드에서 사라지고, 요구사항이 바뀔 때 DB 만 고치면 된다. CRITICAL 27 의 "같은 범위 · 관리자 단축 없음"이 이 코드의 다른 이름이다. 관리자라고 검사를 건너뛰는 분기를 두지 않는다.

### 절대 규칙 셋

신원은 언제나 토큰에서 꺼낸다. `SecurityUtils.getCurrentUserIdOrThrow()`. 클라이언트가 보낸 `userId` 는 관리자 전용 엔드포인트에서만 믿는다. `?userId=123` 자체가 나쁜 게 아니라, 일반 사용자도 부를 수 있는 곳에서 그 값을 믿는 것이 나쁘다.

범위 필터는 검증하지 않고 덮어쓴다. `criteria.setOwnerId(...)`. 검증은 어딘가에서 빠뜨리게 되어 있고 덮어쓰기는 빠뜨리기 어렵다.

목록과 단건의 실패 응답이 다르다. 목록은 빈 결과를, 단건은 403 이 아니라 404 를 준다. 403 을 주면 "그 ID 는 존재한다"는 사실이 새어 나가 ID 를 훑을 수 있게 된다. 실제 코드 주석에도 "타인 결과 — 존재 여부 노출 방지 (404)"라고 적혀 있다.

### SSOT 유지

범위 판정은 유틸 하나에 두고 모든 엔드포인트가 그것을 지나가게 한다. 엔드포인트마다 따로 판정하면 반드시 한 곳이 빠진다. `evaluation/util/MyEvaluationScope.owns(identity, result)` 가 그 예인데, `/my` 계열 네 곳이 전부 이 메서드를 부른다.

---

## 9. 함정 모음

| # | 함정 | 대응 |
|---|---|---|
| 1 | 권한 캐시 — DB 를 직접 UPDATE 하면 반영 안 됨 | `userPermissions`/`userMenus` 캐시(44·78줄). 권한 관리 화면을 통해 변경(172·181줄 `@CacheEvict`)하거나 재로그인 |
| 2 | path 불일치 (`menu-definition.json` ↔ `menu.ts`) | 조용히 실패. 메뉴가 안 보이거나 `unresolved`. 신규 메뉴 사고의 대부분 |
| 3 | `@EnableMethodSecurity(prePostEnabled=true)` 누락 | `@PreAuthorize` 가 에러 없이 무시됨 (보안 설정 3개 + `PermissionSecurityConfig` 에 있음) |
| 4 | `dynamic_roles` 시드 누락 | 새 DB 구축 시 id=1/2/3 필요. `aws-deploy/README.md` 가 가리키는 `seed_dynamic_roles.sql` 은 저장소에 없다 — 빈 DB 로 Flyway 전수 적용을 먼저 검증할 것 |
| 5 | 매트릭스 규칙 순서 | 넓은 규칙을 위에 두면 아래 규칙이 죽는다 |
| 6 | 낡은 주석 | `LocalSecurityConfig` 41줄 주석("JWT 인증 없이")은 사실이 아니다 |
| 7 | FE 기능 권한 갱신 시점 | 로그인 시 `permissionService.me()` 로 `permissions` 를 채운다(`stores/auth.ts` 44줄) → 세션 중 권한 변경은 재로그인 필요 |
| 8 | 메뉴 변경 후 BE 재시작 | `menu-definition.json` → `menus` 테이블 동기화가 기동 시 수행됨 |
| 9 | `hasRole` 신규 추가 | 리뷰·CI 에서 차단된다(CRITICAL 19). `hasFeature` 로 쓴다 |

---

## 10. 자가진단

1. 401 과 403 은 각각 무엇이 문제인가?
2. `JwtAuthenticationFilter` 는 왜 토큰이 틀려도 요청을 통과시키는가?
3. `/api/stt/message` 가 `permitAll` 인데 왜 안전한가?
4. `hasFeature('x:y:delete:all')` 은 매 요청 DB 를 조회하는가? 권한을 DB 에서 바꾸면 언제 반영되나?
5. 일반 사용자가 본인 평가결과를 보게 하려면 메뉴 권한을 줘야 하는가?
6. `?userId=123` 파라미터는 언제 안전하고 언제 위험한가?
7. 단건 조회에서 타인 데이터일 때 403 이 아니라 404 를 주는 이유는?
8. 고객이 "중간관리자에게 삭제 권한 주세요" 라고 하면 배포가 필요한가?
9. 메뉴 이름만 바꾸려면 어디를 고치고, 무엇을 재기동하나?
10. `menu.ts` 를 완전히 없애지 못하는 근본 이유는?

---

## 부록: 파일 위치 요약

| 관심사 | 파일 |
|---|---|
| JWT 검증 | `core/security/JwtAuthenticationFilter.java` (343줄) |
| 토큰 생성 | `core/security/JwtTokenProvider.java` (376줄) |
| URL 매트릭스 (local·test·dev-test) | `core/config/LocalSecurityConfig.java` (391줄) |
| URL 매트릭스 (dev) | `core/config/DevSecurityConfig.java` (304줄) |
| URL 매트릭스 (prod·naver) | `core/config/SecurityConfig.java` (398줄) |
| 로그인 API | `auth/controller/AuthController.java` (`/api/auth/login` 110줄) |
| 사용자 로드 | `auth/service/CustomUserDetailsService.java` |
| 커스텀 권한 함수 | `permission/security/CustomMethodSecurityExpressionRoot.java` |
| 권한 판정·캐시 | `permission/service/impl/DynamicPermissionServiceImpl.java` |
| 메뉴 권한 자동 생성 | `permission/service/impl/DynamicRoleServiceImpl.java` (`PERM_…_ACCESS`) |
| 내 메뉴 API | `permission/controller/UserMenuController.java` (`/my-menus` 52줄) |
| 신원 유틸 | `core/util/SecurityUtils.java` |
| 메뉴 SSOT | `src/main/resources/menu/menu-definition.json` (2,422줄) |
| React 메뉴 레지스트리 | `web-react/src/config/menu.ts` (1,595줄) |
| React 메뉴 수신·병합 | `web-react/src/hooks/use-my-menus.ts` · `web-react/src/lib/menu-merge.ts` |
| React 기능 권한 훅 | `web-react/src/lib/use-permission.ts` |
| React 사이드바 | `web-react/src/components/layout/Sidebar.tsx` |
| 현재 규칙 원문 | `.claude/rules/security-authz-menu.md` (CRITICAL 9 · 19 · 20 · 27) |

---

*문서 끝*
