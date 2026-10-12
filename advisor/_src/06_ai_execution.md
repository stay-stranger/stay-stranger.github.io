# ai 모듈 — 실행 · 프롬프트 · 라우팅

> 1,227개 파일 중 세 길만. 호출자가 프롬프트 유형과 문장을 건네면 모델 사슬에서 하나를 골라 공급자에게 보내고 이력 한 줄을 남기기까지
> 작성 2026-10-12 · 기준 커밋 `f06317ca47` · 로컬 DB 실측
> 선행: 3단계 recording · sttanalytics (자가진단 여덟 문항 이상)

---

## 0. 이 단계의 목표

9월 9일 커밋 메시지에 이런 문장이 있다. "소스에 박혀 있던 gpt-4o · claude-sonnet-4-6 · claude-opus-4-7 · gemini-1.5-flash 는 모델 관리 카탈로그에 존재하지 않는 id 였다. 자동 라우팅을 켜면 등록되지 않은 모델로 호출하고 있었다." 실행 모델 지정 27곳, 프롬프트 25블록, 화면의 모델 상수 18곳을 그날 한 번에 걷어냈다. 그 뒤로 모델과 프롬프트는 코드가 아니라 DB 에 산다. 이 글은 그 DB 세 테이블과, 거기서 값을 꺼내 AI 를 부르는 메서드 하나를 따라간다.

2단계와 3단계에서 AI 를 부르는 자리를 둘 봤다. 평가의 `AIEvaluationService` 와 분류의 `classifyCall`. 둘 다 결국 `AIExecutionOrchestrator` 라는 5,188줄짜리 파일로 들어간다. 다 읽을 필요는 없다. 호출 한 번이 지나는 메서드 셋만 보면 나머지 1,200개 파일이 그 주변에 어떻게 붙어 있는지 보인다.

### 7월 가이드 뒤에 바뀐 것

| 항목 | 7월 27일 | 지금 |
|---|---|---|
| `ai` Java 파일 | 866 | 1,227 (커밋 329개) |
| `ai/execution` | 231 | 466 |
| `ai/prompt` | 399 | 467 |
| `ai/routing` | 4 | 4 |
| `ai/execution/routing` | — | 120 |

7월 가이드는 세 패키지를 `execution` · `prompt` · `routing` 이라고 적었다. 그중 `ai/routing/` 은 틀렸다. 거기에는 채팅 화면의 Smart Routing 넷뿐이고 `enabled: false` 가 기본이다. 모델을 고르고 실패하면 다음으로 넘기는 일은 `ai/execution/routing/` 120개가 한다. 9월 3일부터 18일 사이에 지어진 패키지라 7월에는 없었다. 가이드의 표를 고쳤다.

석 달 동안 이 모듈에 329개 커밋이 들어왔다. 저장소 전체에서 가장 많이 손댄 자리다. 그래도 호출 한 번이 지나는 길은 하나고, 그 길에 붙은 이름들만 바뀌었다.

---

## 1. 이 모듈이 하는 일 (한 문장)

호출자가 프롬프트 유형과 문장을 주면, 그 유형에 묶인 모델 사슬에서 첫 번째를 골라 공급자 클라이언트로 보내고, 실패하면 다음 모델로 넘기고, 끝나면 이력 한 줄을 남긴다.

```
 호출자 (evaluation · sttanalytics · kms · chat · agi …)
   │  execute(prompt, promptType, format, executedBy)   또는  executeWithModel(modelId, …)
   ▼
 AIExecutionOrchestrator (5,188줄)
   ① 유형 → 모델 사슬      prompt_type_model_mapping (없으면 전역 우선순위)
   ② 사슬 순서대로 시도     executeWithPriorityFallbackAttempts        ← 정책이 있으면 ai/execution/routing 이 순서를 준다
   ③ 모델 하나 실행         executeWithModelInternal
        이력 열기 → 과금 가드 → API 키 → 클라이언트 → 토큰 상한 → 요청 조립 → 호출 → 이력 닫기
   ▼
 AIProviderClient 다섯   Gemini · OpenAI · Anthropic · vLLM · Ollama
   ▼
 ai_execution_history (호출 한 줄)   +   ai_execution_request / attempt (후보 사슬과 시도)
```

이 모듈은 교환대다. 전화를 거는 쪽은 번호를 모른다. 용건(프롬프트 유형)만 말하면 교환원이 장부에서 그 용건에 배정된 회선 순서를 찾아 첫 회선에 꽂고, 통화 중이면 다음 회선으로 돌린다. 장부가 `prompt_type_model_mapping` 이고 회선이 `ai_model_configuration` 이다. 비유는 여기까지다. 장부에 없는 용건이면 전역 우선순위라는 두 번째 장부를 본다는 것까지가 사실이다.

---

## 2. 읽는 순서 (7개 파일, 이 순서대로)

| # | 파일 | 줄 수 | 읽는 법 |
|---|---|---|---|
| 1 | `ai/execution/entity/AIModelConfiguration.java` | 507 | 상단 컬럼. `provider` · `model_id` · `priority` · `is_active` 넷이면 된다 |
| 2 | `ai/execution/service/PromptTypeModelMappingService.java` | — | 194줄 `getActiveModelsByPromptTypeName` 과 211줄 `hasDesignatedModels` |
| 3 | `ai/prompt/entity/AIPromptTemplate.java` + `ai/prompt/runtime/PromptTemplateRuntime.java` | 219 · — | 엔티티는 컬럼만. 런타임은 47~60줄 `renderDefault` |
| 4 | DB SELECT | — | 4절 쿼리 넷 |
| 5 | `ai/execution/service/AIExecutionOrchestrator.java` | 5,188 | 757~813줄 `execute`, 4145줄 `executeWithPriorityFallbackAttempts`, 949~1140줄 `executeWithModelInternal` |
| 6 | `ai/execution/client/AIProviderClient.java` | — | 인터페이스 전부. 구현은 `AnthropicProviderClient` 248줄 `execute` 하나만 |
| 7 | `ai/execution/entity/AIExecutionHistory.java` | 466 | 컬럼. 4절 3번 쿼리가 이 테이블이다 |

5번 파일이 오천 줄이다. 2단계 2,166줄, 3단계 2,086줄 다음이라 이제 익숙할 것이다. 메서드 셋만 보고, 그 셋이 부르는 것 중 이름만 외워 둘 것이 넷이다. `buildTryOrderWithSelectionType` (4551줄), `resolveApiKey`, `clientFactory.getClient`, `trackingService.recordExecutionAsync`.

---

## 3. entity — 이 도메인의 "명사" 넷

| 엔티티 | 테이블 | 한 줄 | 로컬 행 수 |
|---|---|---|---|
| `AIModelConfiguration` | `ai_model_configuration` | 회선 하나. 공급자 · 모델 id · 엔드포인트 · 우선순위 · 단가 | 65 (활성 20) |
| `PromptType` (엔티티) + `AIPromptTemplate` | `prompt_type` · `ai_prompt_template` | 용건 198개와 그 용건의 문장 틀 241개 | 198 · 241 |
| `PromptTypeModelMapping` | `prompt_type_model_mapping` | 용건마다 회선 순서. 55개 용건이 묶여 있다 | 126 |
| `AIExecutionHistory` | `ai_execution_history` | 호출 한 줄. 모델 · 토큰 · 시간 · 비용 · 성공 여부 | 7,879 |

9월 18일부터 셋이 더 붙었다. `model_routing_policy` (88) 가 용건별 후보 사슬을 버전으로 발행하고, `ai_execution_request` (290) 와 `ai_execution_attempt` (335) 가 요청 하나에 후보 몇을 어떤 순서로 시도했는지 남긴다. `ai_execution_history` 가 "어느 모델이 답했나"라면 이 둘은 "어느 모델들을 거쳐 거기 닿았나"다. 로컬에는 9월 18일 이후의 290건만 있다.

### 3.1 `PromptType` 이 둘이다

`ai/prompt/enums/PromptType.java` 에 enum 이 198개 있고, `prompt_type` 테이블에도 198줄이 있다. 같은 이름이고 같은 수다. enum 은 코드가 용건을 부를 때 쓰는 이름이고, 테이블은 화면이 보여 주고 템플릿과 매핑이 외래키로 가리키는 쪽이다. `AIPromptDataInitializer` (4,333줄) 가 서버 기동 때 테이블이 비어 있으면 용건 목록과 기본 템플릿을 채운다. 둘이 어긋나면 코드가 부르는 용건에 템플릿이 없다는 뜻이고, 그때 `renderDefault` 가 던지는 예외가 "기본 템플릿 없음"이다.

용건 하나에 템플릿이 여럿일 수 있고 그중 `is_default` 가 하나다. `COUNSEL_TYPE_CLASSIFY` 는 v1 부터 v4 까지 네 장이 있고 v4 만 활성이자 기본이다. 2,605자다. 3단계 `classifyCall` 이 `loadActiveTemplate` 으로 꺼내 가는 것이 이 한 장이다.

### 3.2 모델 사슬 — `EVALUATION` 의 넷

| 순위 | 공급자 | 모델 |
|---|---|---|
| 1 | ANTHROPIC | `claude-haiku-4-5-20251001` |
| 2 | OLLAMA | `ollama-exaone3.5:7.8b` |
| 3 | ANTHROPIC | `claude-sonnet-4-5-20250929` |
| 4 | VLLM | `gemma-4-12b` |

2단계의 평가 호출이 타는 사슬이다. 4절 3번 쿼리를 치면 로컬 평가 2,951건 중 2,945건이 1순위에서 끝났고 5건이 2순위, 1건이 3순위까지 갔다. 1순위의 평균 응답이 2,715ms 다. 2단계에서 "문항 하나에 5초쯤"이라고 적은 것 중 2.7초가 여기고 나머지는 근거 색인과 저장이다.

---

## 4. DB 실습 — 코드 전에 데이터부터

```bash
docker exec -it mariadb mariadb -u <계정> -p local_db
```

```sql
-- 1) 회선. 공급자별로 몇 개가 켜져 있나
SELECT provider, COUNT(*) n, SUM(is_active+0) active FROM ai_model_configuration GROUP BY 1;

-- 2) 장부. 평가 용건에 묶인 모델 순서
SELECT p.name AS prompt_type, m.priority, c.provider, c.model_id
FROM prompt_type_model_mapping m
JOIN prompt_type p ON p.id = m.prompt_type_id
JOIN ai_model_configuration c ON c.id = m.model_id
WHERE p.name = 'EVALUATION' ORDER BY m.priority;

-- 3) 이력. 용건별로 어느 모델이 몇 번, 얼마나 걸려 답했나
SELECT prompt_type, model_id, COUNT(*) n, ROUND(AVG(response_time_ms)) ms, SUM(is_success+0) ok
FROM ai_execution_history GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10;

-- 4) 9월 18일 이후의 요청. 후보를 어디서 골랐고 어떻게 끝났나
SELECT selection_origin, route_result, COUNT(*) n
FROM ai_execution_request GROUP BY 1, 2 ORDER BY 3 DESC;
```

1번은 여섯 줄이다. Ollama 28개 중 2개, OpenAI 10개 중 0개, Gemini 10개 전부, Anthropic 6개 중 3개, vLLM 9개 중 3개, 음성 인식용 둘. 활성 20개 중 유료 공급자의 키는 `ai_model_credential` 다섯 줄에 있다. 환경변수가 아니다. 9월 15일 커밋이 헬스체크까지 그 테이블을 보게 고쳤다. 그 전에는 운영 로그에 폴링마다 "API 키 환경변수가 없다"는 경고가 찍히면서 정작 호출은 되고 있었다.

3번이 이 글에서 가장 오래 볼 결과다. 7,879건 중 `EVALUATION` 2,951건과 `AI_EVALUATION` 2,426건이 있다. 둘은 같은 용건이다. `PromptTypeAliasRegistry` 가 `AI_EVALUATION` 을 `EVALUATION` 으로 바꿔 주는데, 이력에는 바꾸기 전 이름으로 적힌 옛 행이 남아 있다. 통계를 낼 때 둘을 합치지 않으면 평가 호출이 절반으로 보인다. 맨 아래 다섯 줄은 10월 9일 오후의 `FRAGMENT_GENERATOR` 실패 다섯이고 300ms 씩이다. 공급자가 400 으로 돌려보낸 것이고, `ai_execution_attempt` 에 같은 `PROVIDER_ERROR` · 400 이 114건 쌓여 있다.

4번은 290줄 중 266줄이 같은 `FRAGMENT_GENERATOR` 다. `GLOBAL_DEFAULT` 로 고른 것이 152건 성공, 124건 실패. `PROMPT_TYPE` 으로 고른 것이 12건이고 그중 8건이 `FALLBACK_SUCCESS` 다. 1순위가 죽어 2순위가 답한 요청이 여덟 있었다는 뜻이다. 어느 모델이 죽었는지는 `ai_execution_attempt` 의 `skip_reason` 과 `failure_code` 에 있다.

> 💡 **이력은 호출보다 먼저 열린다.** `executeWithModelInternal` 은 공급자를 부르기 전에 `startOwnedHistory` 로 요청 행을 만든다. 과금 가드에 막히거나 API 키가 없어 호출 자체를 못 한 실패도 그래서 이력에 남는다. 예전에는 요청 조립 뒤에 열어서 그런 실패가 통째로 빠졌다. 949줄 아래 주석이 그 사연이다.

---

## 5. 모델 고르기 — `execute` 에서 시도 순서까지

### 5.1 `execute` (757~813줄) — 장부 셋

`execute(userPrompt, promptType, format, executedBy)` 의 오버로드 다섯이 전부 757줄 하나로 모인다. 거기서 모델을 고르는 순서가 셋이다.

첫째, 중앙 라우팅. `routingGateway` 가 주입되어 있고 예산 제약이 없으면 `routingGateway.execute(...)` 로 넘긴다. 게이트웨이는 `OrchestratorRoutingPlanner.resolve` 로 정책을 찾고, 정책이 있으면 그 후보 순서가 곧 시도 순서다. 후보마다 `executeWithModel` 을 부르는 람다를 넘기므로 실제 호출은 결국 6절로 돌아온다. 정책이 없으면 "종전 경로를 그대로 탄다". 이관 전 환경에서 배포가 동작을 바꾸지 않게 하려고 둔 문장이다.

둘째, 용건 장부. `promptTypeModelMappingService.hasDesignatedModels(promptType)` 이 참이면 `executeWithPriorityFallback` 으로 들어간다. 로컬에서 55개 용건이 여기 걸린다.

셋째, 전역 우선순위. 장부에 없는 용건은 `modelService.getHighestPriorityModel()` 로 활성 모델 중 `priority` 가 가장 낮은 것을 1순위로 잡는다. 예산이 지정되면 그 안에서 가장 좋은 모델을 고른다.

### 5.2 `executeWithPriorityFallbackAttempts` (4145줄) — 시도 순서는 저장된 그대로

`buildTryOrderWithSelectionType` (4551줄) 이 시도 목록을 만든다. 정책이 발행되어 있으면 그 순서, 아니면 수동 지정 모델 → 용건 장부 순서 → 전역 우선순위를 이어 붙인다. 9월 14일에 규칙 하나가 바뀌었다. 그 전에는 지정 모델이 죽으면 거기서 끝이었는데, 지금은 지정 모델 뒤에 용건 사슬과 전역 사슬을 붙인다. `disableFallback=true` 로 부른 호출만 예외다. 화자 분리처럼 자기 루프로 모델을 고르는 기능이 그 예외를 쓴다.

목록이 만들어지면 그 순서를 바꾸지 않는다. 종전에는 모델의 online 판정으로 재정렬했는데, 그러면 사용자가 화면에서 저장한 1·2·3 순위가 실제 순서가 아니게 되어 화면과 실행이 어긋났다. 지금은 루프 안의 오프라인 게이트가 죽은 모델을 건너뛸 뿐 순서는 그대로다. 게이트는 `app.ai.execution.offline-skip-enabled` 로 끌 수 있고 기본 켜짐이다.

루프 안에서 모델마다 Circuit Breaker 하나씩이다. `aiExecution` 인스턴스의 설정을 복제해 모델 이름으로 하나를 만들고, 열려 있으면 바로 다음 모델이다. 한 모델이 연달아 실패해도 다른 모델의 회로는 닫혀 있다.

---

## 6. 호출 한 번 — `executeWithModelInternal` (949~1140줄)

2단계의 `executeEvaluation` 처럼 줄을 따라가면 된다. 번호는 코드의 순서다.

처음 둘은 이름과 모델이다. `PromptTypeAliasRegistry.canonicalize` 가 `AI_EVALUATION` 을 `EVALUATION` 으로 바꾸고, `modelId` 가 비었으면 용건 장부에서 online 우선으로 고르거나 없으면 전역 활성 모델에서 고른다. 그다음 `modelService.getModelByIdOrThrow` 로 회선 한 줄을 읽는다. 셋째가 `startOwnedHistory` 다. 4절의 노트가 말한 그 자리로, 공급자를 부르기 전에 이력이 먼저 열린다.

넷째와 다섯째가 돈과 열쇠다. `enforceBillingQuota` 가 사용자·기능 쿼터를, `enforceBillingGuard` 가 유료 공급자 차단 스위치와 일일 상한과 허용 목록을 본다. 로컬 모델은 가드를 그냥 지난다. API 키는 Ollama 와 vLLM 이면 건너뛰고, 나머지는 `resolveApiKey` 가 `ai_model_credential` → 설정값 → 환경변수 순으로 찾는다. 없으면 예외를 던지고 상위 루프가 다음 모델로 간다.

여섯째부터 여덟째는 요청을 만드는 일이다. `clientFactory.getClient(provider)` 가 다섯 클라이언트 중 하나를 주고, `applyMaxTokenCap` 이 `application.yml` 의 `ai.prompt-output.limits` 에서 용건별 출력 토큰 상한을 꺼내 얹는다. `NLP_NER` 256, `ASSIST_SUMMARY_FINAL` 1500 같은 식이다. `buildRequest` 가 모델 설정의 온도와 top_p 와 엔드포인트를 요청에 싣는다.

아홉째가 `executeWithRetry(client, request, model, promptType)` 다. 취소 폴링과 Ollama 장애 전환이 이 안에 있고 `@Retry` 는 없다. 저장소 규칙 11번이 LLM 호출에 `@Retry` 를 금지한다. 같은 입력에 다른 답이 나올 수 있고 토큰 비용이 배로 뛰기 때문이다. 열째가 `trackingService.recordExecutionAsync` 로, 비동기로 `ai_execution_history` 한 줄을 닫는다.

다섯째가 2단계와 3단계의 호출이 서로 다른 모델을 쓰게 되는 이유다. 평가는 `claude-haiku` 가 1순위라 키가 필요하고, 분류의 `COUNSEL_TYPE_CLASSIFY` 는 장부에도 정책에도 없어서 전역 우선순위를 탄다. 전역 1순위가 무엇인지는 1번 쿼리의 `priority` 가 말해 준다.

### 가드레일과 캐시는 이 길에 없다

`ai/execution/guardrail` 열여섯과 `ai/execution/cache` 서른하나는 `AiGatewayFacadeServiceImpl` 이 쓴다. `/api/agi/gateway/v1` 로 들어오는 OpenAI 호환 바깥 요청에 입력 레일(PII 마스킹 · 탈옥 탐지), 시맨틱 캐시(pgvector 유사도 0.95), 출력 레일을 건다. 오케스트레이터를 직접 부르는 평가와 분류는 그 레일을 지나지 않는다. 안에서 부르는 호출은 신뢰하는 설계다.

---

## 7. 프롬프트 — 코드에서 DB 로

`PromptTemplateRuntime.renderDefault(promptType, variables)` 가 전부다. `getDefaultTemplateByTypeOrThrow` 로 기본 템플릿 한 장을 꺼내고 `{{name}}` 자리에 변수를 끼운다. 2단계의 `EVALUATION_OUTPUT_CONTRACT` 379자, 3단계의 `COUNSEL_TYPE_CLASSIFY` v4 2,605자가 그렇게 나온다. `renderDefaultOrFallback` 은 템플릿이 없을 때 코드의 상수를 쓰는 변형이고, 2단계 `resolveOutputContract` 가 그것을 쓴다.

9월 9일 전에는 프롬프트 53블록이 코드에 있었다. 28은 이미 DB 우선의 폴백이었고 25가 프롬프트 관리를 우회하는 실행 경로였다. 그날 유형 13종을 새로 만들고 25블록을 `PromptTemplateRuntime` 으로 배선했다. 자리표시자 규약도 `%s` 에서 `{{name}}` 으로 바꿨고, `requiredKeys` 로 화면에서 변수 이름을 지우는 사고를 막는다. 그 커밋이 Flyway 23개를 7개로 합치면서 로컬 DB 이력 20행을 백업 테이블로 옮기고 다시 적용했다.

`ai/prompt` 467개 중 239개가 `quality` 다. 프롬프트 품질 로그(`prompt_quality_log` 868줄), 진단, 개선 제안, 효과 추적이다. 2단계 `evaluateWithPrompt` 가 `PromptQualityLogger` 로 한 줄씩 남기는 곳이 여기다. `fragment` 122개는 프롬프트 조각 라이브러리와 A/B 실험이다. 둘 다 이번에는 이름만 외운다.

---

## 8. 다음 단계로 가는 다리

오케스트레이터를 자기 밖에서 부르는 모듈이 서른하나다. `agi` 38곳, `orchestration` 23곳, `kms` 17곳, `chat` 12곳. 5단계 `rag` 와 `kms` 는 `RAG_QUERY` 와 `RAG_ANSWER_GENERATION` 용건으로 이 길을 탄다. 4절 3번 쿼리에 `RAG_QUERY` 106건이 있다. 5단계는 그 106건이 어떤 질문을 어떤 문서와 함께 보냈는지, 즉 프롬프트에 끼워 넣는 `variables` 가 어디서 오는지를 본다. `kms` 774개 파일은 그 문서를 만들고 찾는 쪽이다.

---

## 9. 함정 모음

1. **`ai/routing/` 은 라우팅이 아니다.** 채팅 Smart Routing 넷이고 기본 꺼짐. 모델 선택과 폴백은 `ai/execution/routing/` 120개와 오케스트레이터 4145줄이다.
2. **`AI_EVALUATION` 과 `EVALUATION` 은 같은 용건이다.** 이력에 두 이름이 섞여 있다. 합쳐서 세지 않으면 평가 호출이 절반이다.
3. **시도 순서는 저장된 그대로다.** online 판정으로 재정렬하지 않는다. 1순위가 죽어 있으면 게이트가 건너뛰고 순서는 유지된다. 화면의 순서와 실행의 순서가 같아야 한다는 결정이다.
4. **정책이 있으면 정책이 이긴다.** `model_routing_policy` 에 `PUBLISHED` 가 있으면 용건 장부보다 그 순서가 먼저다. 로컬의 88개는 전부 9월 18일 이관 때 들어온 `PUBLISHED` 다. "장부를 고쳤는데 순서가 안 바뀐다"면 정책을 본다.
5. **API 키는 DB 에 있다.** `ai_model_credential` → 설정값 → 환경변수 순. 환경변수만 세팅하고 호출이 안 되면 테이블에 비활성 키가 먼저 걸린 것일 수 있다.
6. **LLM 호출에 `@Retry` 를 붙이지 않는다.** 규칙 11번. Circuit Breaker 만 쓴다. `AIProviderClient` 66줄 주석이 클라이언트 쪽 CB 미적용을 "알려진 부채"로 적어 두었다.
7. **가드레일과 캐시는 게이트웨이 경로에만 있다.** 안에서 부르는 호출은 레일을 지나지 않는다.
8. **토큰 상한은 yml 이 정한다.** 모델의 `max_tokens` 가 아니라 `ai.prompt-output.limits` 의 용건별 값이 요청에 실린다. 답이 잘리면 여기부터.
9. **합의 평가는 호출을 세 배로 만든다.** 2단계의 `consensus-enabled` 가 켜진 환경에서는 문항 하나에 이 길을 세 번 지난다. 이력 건수로 비용을 추정할 때 나눠야 한다.

---

## 10. 자가진단

1. `execute` 가 모델을 고르는 세 장부의 순서.
2. 로컬에서 `EVALUATION` 용건의 1순위 모델과 평균 응답 시간.
3. `ai/routing/` 과 `ai/execution/routing/` 의 차이.
4. `executeWithModelInternal` 에서 이력이 열리는 시점과 그 이유.
5. Ollama 와 vLLM 이 건너뛰는 단계.
6. `PromptType` 이 둘인 이유와 둘을 맞추는 컴포넌트.
7. `COUNSEL_TYPE_CLASSIFY` 가 전역 우선순위를 타는 이유.
8. 시도 순서를 online 상태로 재정렬하지 않는 이유.
9. 9월 9일 커밋이 걷어낸 세 가지와 그 숫자.
10. 가드레일이 적용되는 진입점과 적용되지 않는 진입점.

여덟 이상이면 5단계로 간다. 5단계는 `rag` 274개와 `kms` 774개다. 이 글의 `RAG_QUERY` 106건이 무엇을 물었는지가 거기 첫 질문이다.

---

## 부록: 파일 위치 요약

| 관심사 | 파일 | 줄 |
|---|---|---|
| 회선 (모델 설정) | `ai/execution/entity/AIModelConfiguration.java` | 507 |
| 용건 장부 (유형→모델) | `ai/execution/service/PromptTypeModelMappingService.java` | 194 · 211 |
| 진입 · 사슬 · 호출 한 번 | `ai/execution/service/AIExecutionOrchestrator.java` | 757 · 4145 · 949 |
| 시도 순서 조립 | 같은 파일 | 4551 |
| 중앙 라우팅 게이트웨이 · 계획 | `ai/execution/routing/service/impl/RoutingExecutionGatewayImpl.java` · `OrchestratorRoutingPlanner.java` | 41 · 159 |
| 공급자 계약 · 구현 다섯 | `ai/execution/client/AIProviderClient.java` · `*ProviderClient.java` | 43 |
| 클라이언트 팩토리 | `ai/execution/client/AIProviderClientFactory.java` | 52 |
| 이력 쓰기 | `ai/execution/service/AIExecutionTrackingService.java` | 119 |
| 이력 · 요청 · 시도 엔티티 | `ai/execution/entity/AIExecutionHistory.java` · `routing/entity/RoutingExecution{Request,Attempt}Entity.java` | 466 |
| 용건 enum · 엔티티 · 템플릿 | `ai/prompt/enums/PromptType.java` · `prompt/entity/PromptType.java` · `AIPromptTemplate.java` | 881 · 82 · 219 |
| 템플릿 렌더 | `ai/prompt/runtime/PromptTemplateRuntime.java` | 47 |
| 기동 시 시드 | `ai/prompt/config/AIPromptDataInitializer.java` | 4,333 |
| 별칭 | `ai/execution/service/PromptTypeAliasRegistry.java` | 15 |
| 게이트웨이 (가드레일 · 캐시) | `ai/execution/gateway/AiGatewayFacadeServiceImpl.java` | 241 · 263 · 310 |
| 레거시 래퍼 (평가가 쓰는 입구) | `ai/service/AiModelFallbackClient.java` | 144 |
| 설정 (출력 토큰 상한 · 오프라인 게이트) | `application.yml` | `ai.prompt-output.limits` · `app.ai.execution.offline-skip-enabled` |
| 결정 기록 | `docs/harness/decisions/2026-09-07-ai-routing-w05-execution-contract.md` 외 9월 15일 넷 | — |
| 화면 | `web-react/src/pages/AiModelManagementPage.tsx` · `AiPromptManagementPage.tsx` · `AiExecutionPlatformPage.tsx` | — |

*문서 끝*
