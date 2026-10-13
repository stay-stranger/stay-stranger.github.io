# rag · kms — 검색과 지식

> 문서 한 장이 게시 버튼을 지나 벡터 183개 중 몇 줄이 되고, 질문 하나가 그 줄들을 어떻게 다시 찾아 답이 되는가
> 작성 2026-10-13 · 기준 커밋 `f06317ca47` · 로컬 DB(MariaDB + PostgreSQL) 실측
> 선행: 4단계 ai 모듈 (자가진단 여덟 문항 이상)

---

## 0. 이 단계의 목표

PostgreSQL 에서 벡터를 세었더니 183개였다. 문서로는 29건. MariaDB 로 건너가 그 29건을 찾아보니 하나는 번호가 0이고 제목이 비어 있는 테스트 잔재였고, 하나는 74번인데 승인 상태가 `PENDING` 이었다. 게시된 적 없는 문서의 문장이 검색 가능한 벡터로 앉아 있었다. 2단계부터 4단계까지 "코드 전에 데이터"를 세 번 했는데, DB 가 둘인 모듈에서는 두 DB 를 맞대 봐야 보이는 것이 있다.

이 단계는 `rag` 274개와 `kms` 774개를 한 글에 묶는다. 둘 사이에 `flowbox` 66개가 다리로 끼어 있어서 실제로는 셋이다. 전부 읽지 않는다. 문서 한 장이 게시 버튼을 지나 벡터가 되는 길 하나, 질문 하나가 그 벡터를 찾아 답이 되는 길 하나, 그 둘만 끝까지 따라간다. 4단계에서 남긴 질문, `RAG_QUERY` 106건이 무엇을 물었는가도 여기서 답이 난다.

### 7월 가이드 뒤에 바뀐 것

| 항목 | 7월 27일 | 지금 |
|---|---|---|
| `rag` Java 파일 | 209 | 274 (커밋 85개) |
| `kms` Java 파일 | 588 | 774 (커밋 163개) |
| `flowbox` (다리) | — | 66 |
| 벡터 테이블 | — | `knowledge_base_vectors` 183개 · 1,024차원 · HNSW m=24 |

8월 21일에 납품 범위에 KMS 가 들어오면서 지식관리 · 색인 · 검색을 한 사슬로 놓고 고치기 시작했다. 9월 4일 운영에서 제목 검색이 0건 나오던 결함(아래 9절), 9월 8일부터 11일까지 문서 버전 이력, 9월 24일 재색인 뒤 10분간 옛 결과를 주던 캐시가 그 사슬에서 나온 수정이다. `kms` 의 163개 커밋 중 절반이 9월 한 달에 몰려 있다.

---

## 1. 세 모듈이 하는 일 (한 문장씩)

`kms` 는 지식 문서를 쓰고, 승인하고, 게시하고, 버전을 남기는 서고다. `flowbox` 는 게시된 문서를 받아 색인 요청으로 바꾸고 색인 상태를 문서별로 기록하는 접수대다. `rag` 는 그 문서를 잘라 벡터로 만들어 PostgreSQL 에 넣고, 질문이 오면 벡터와 키워드 두 길로 찾아 섞고 다시 순위를 매겨 돌려주는 사서다.

```
 [쓰기]  kms  KnowledgeArticle  DRAFT → PENDING → APPROVED ──publishArticle──▶ is_published=1
                                                                  │ KnowledgeArticlePublishedEvent (커밋 뒤)
         flowbox  KmsArticleEventListener ──▶ KmsIndexingServiceImpl.indexDocument   document_index_status: PROCESSING → COMPLETED
                                                                  │
         rag      DocumentIndexingServiceImpl.indexDocument  HTML 벗기기 → 500자 청크 → 임베딩(사이드카 10503) → PG upsert

 [읽기]  질문 ──▶ KoreanSearchServiceImpl.hybridSearch
                   범위 확정 → 임베딩 ∥ 토큰화 → 캐시 → SQL(벡터 ∪ 키워드, RRF) → 리랭커 → 감사 로그
                 ──▶ 답변 생성 (RAG_ANSWER_GENERATION 또는 AI_EXPERT_CHAT) ──▶ 4단계의 문
```

서고와 사서가 다른 건물에 있다. 서고는 MariaDB 고 사서의 카드 목록은 PostgreSQL 이다. 두 건물 사이를 오가는 것은 문서 번호 하나뿐이다. `knowledge_base_vectors.document_id` 가 `knowledge_article.id` 다. 외래키는 없다. 그래서 서고에 없는 카드가 생길 수 있고, 0절의 번호 0 카드가 그런 경우다.

---

## 2. 읽는 순서 (8개 파일, 이 순서대로)

| # | 파일 | 줄 수 | 읽는 법 |
|---|---|---|---|
| 1 | `kms/entity/KnowledgeArticle.java` | 654 | 상단 컬럼. `approvalStatus` · `isPublished` · `indexExcluded` · `isTrashed` 넷이 서빙 조건이다 |
| 2 | `rag/korean/entity/KnowledgeBaseVector.java` | 223 | 전부. 컬럼 열 개 |
| 3 | DB SELECT | — | 4절. MariaDB 둘, PostgreSQL 둘 |
| 4 | `kms/service/impl/KnowledgeArticleServiceImpl.java` | 4,276 | 1564줄 `publishArticle` 만 |
| 5 | `flowbox/event/KmsArticleEventListener.java` | 467 | 190줄 `handleArticlePublished` 와 101줄 `handleArticleUpdated` |
| 6 | `flowbox/service/impl/KmsIndexingServiceImpl.java` | 1,954 | 333~430줄 `indexDocument`. 짧은 트랜잭션과 바깥 I/O 의 경계 |
| 7 | `rag/korean/service/impl/DocumentIndexingServiceImpl.java` | 3,833 | 316줄 `indexDocument`, 994줄 `htmlToPlainText`, 1040줄 `chunkText` |
| 8 | `rag/korean/service/impl/KoreanSearchServiceImpl.java` + `repository/VectorRepository.java` | 3,855 · 1,154 | 280줄 `hybridSearch` 와 743줄 하이브리드 SQL |

4번과 7번과 8번이 각각 사천 줄이다. 세 파일 합쳐 만 이천 줄이지만 메서드로 치면 다섯이다. 2단계부터 같은 말을 해 왔으니 이번에는 줄이겠다.

---

## 3. entity — 이 도메인의 "명사" 넷

| 엔티티 | 저장소 · 테이블 | 한 줄 | 로컬 행 수 |
|---|---|---|---|
| `KnowledgeArticle` | MariaDB `knowledge_article` | 문서 한 장. 본문은 HTML 과 평문 둘 다 | 62 (휴지통 제외 47) |
| `KnowledgeVersion` · `KMSChapter` | MariaDB `knowledge_version` · `kms_chapter` | 문서의 이력 행과 문서가 꽂힌 챕터 | 54 · 8 |
| `DocumentIndexStatus` | MariaDB `document_index_status` | 문서별 색인 상태. `flowbox` 가 쓴다 | 28 |
| `KnowledgeBaseVector` | PostgreSQL `knowledge_base_vectors` | 청크 하나. 1,024차원 벡터와 키워드 색인 | 183 |

`KnowledgeArticle` 은 컬럼이 쉰 개가 넘는다. 넷만 외운다. `approval_status` (`DRAFT` `PENDING` `APPROVED` `REJECTED` `EXPIRED`), `is_published`, `index_excluded`, `is_trashed`. 상담사 화면의 문서 검색은 이 넷을 한 조건으로 묶은 `servingOnly` 를 쓴다. 승인되었고, 게시되었고, 색인 제외가 아니고, 유효기간 안이어야 보인다. `KnowledgeArticleRepository` 81줄의 `SERVING_ONLY_JPQL` 이 그 문장이고, 네이티브 SQL 판이 바로 아래 있다. 9월 4일 전에는 이 조건이 없어서 초안과 반려 문서가 검색에 떴다.

`KnowledgeBaseVector` 는 열 컬럼이다. `document_id` 와 `chunk_index` 와 `field_type` 셋이 유일키다. `field_type` 은 `BODY` · `TITLE` · `ATTACHMENT` 다. 로컬 183개 중 본문 154, 제목 26, 첨부 3. 한 문서가 제목 벡터 하나와 본문 벡터 여럿으로 쪼개져 들어간다. `embedding` 은 `vector(1024)` 이고 `content_tsvector` 는 PostgreSQL 이 본문에서 계산하는 키워드 색인이라 JPA 에 매핑하지 않는다.

`DocumentIndexStatus` 의 상태가 다섯이다. `PENDING → PROCESSING → COMPLETED`, 본문이 바뀌면 `UPDATE_REQUIRED`, 색인 제외면 `EXCLUDED`. 2단계 평가 대상의 `DATA_READY` 처럼 "다시 색인해야 하는가"를 이 한 컬럼이 말한다.

---

## 4. DB 실습 — 두 건물을 맞대 본다

```bash
docker exec -it mariadb mariadb -u <계정> -p local_db
docker exec -it pgvector psql -U <계정> -d <db>
```

```sql
-- 1) [MariaDB] 서고. 상태별 문서 수
SELECT approval_status, is_published+0 AS pub, index_excluded+0 AS excl, COUNT(*)
FROM knowledge_article WHERE is_trashed = 0 GROUP BY 1, 2, 3;

-- 2) [MariaDB] 접수대. 색인 상태와 청크 수
SELECT status, COUNT(*) n, SUM(chunk_count) chunks FROM document_index_status GROUP BY 1;

-- 3) [PostgreSQL] 카드 목록. 문서별 벡터 수와 필드
SELECT document_id, field_type, COUNT(*) FROM knowledge_base_vectors GROUP BY 1, 2 ORDER BY 1 DESC LIMIT 12;

-- 4) [PostgreSQL] 검색 로그. 모드별 건수 · 평균 시간 · 평균 결과 수
SELECT search_mode, COUNT(*), ROUND(AVG(execution_time_ms)) ms, ROUND(AVG(result_count), 1) results
FROM search_queries GROUP BY 1;
```

1번은 다섯 줄이다. 승인·게시 26, 승인·미게시 2, 초안 15, 검토 대기 3, 반려 1. 상담사에게 보이는 것은 26이다. 2번은 `COMPLETED` 22건에 청크 105개, `UPDATE_REQUIRED` 6건에 청크 51개. 여섯 문서는 본문이 바뀐 뒤 아직 재색인되지 않았고, 그 사이 검색은 옛 청크 51개로 답한다.

3번을 1번과 맞대면 0절의 두 문서가 나온다. 번호 0은 제목 없이 "상세한 내용이 여기에 들어갑니다"라는 본문 한 줄이다. 74번은 10월 2일의 첨부 이미지 미리보기 실측 문서인데 `PENDING` 이면서 제목 · 본문 · 첨부 벡터 셋이 다 있다. 가져오기 화면이 문서를 만들자마자 `autoIndex` 로 색인을 걸기 때문이다. `DocumentImportController` 341줄이다. 승인은 `autoApprove` 라는 다른 옵션이고 기본값이 꺼짐이라, 가져온 문서는 승인 전에 카드부터 생긴다. 5절의 게시 경로와 다른 두 번째 입구다.

4번은 2,192건이다. `HYBRID` 2,086건이 평균 353ms 에 3.6건, `KEYWORD` 106건이 152ms 에 0.2건. 월별로 세면 7월 한 달에 1,802건이 몰려 있다. 2단계의 평가 사실검증이 통화마다 지식을 찾던 때다. 4단계에서 본 `RAG_QUERY` 106건이 무엇을 물었는지는 `query_text` 에 있다. 90일 뒤에 지우는 배치가 돈다.

> 💡 **검색은 PostgreSQL 만 본다.** 하이브리드 SQL 은 `knowledge_base_vectors` 안에서만 돈다. 승인 상태는 MariaDB 에 있어서 SQL 이 모른다. 게시된 문서만 검색되는 것은 색인 입구가 게시 이벤트이기 때문이지 검색이 걸러서가 아니다. 그래서 가져오기처럼 다른 입구로 들어온 카드는 그대로 검색된다. `/api/kms/ask` 는 그 구멍을 `servingArticleIds` 로 한 번 더 막는다(7절).

---

## 5. 색인 — 게시 버튼에서 벡터까지

### 5.1 `publishArticle` (1564줄) — 잠그고, 다시 읽고, 도장 찍고, 알린다

`versionRecorder.lockArticle(article)` 로 문서 행을 `FOR UPDATE` 잠그고 `entityManager.refresh` 로 다시 읽는다. 잠그기 전에 읽은 값으로 수정하면 동시 편집을 옛 행으로 덮어쓰기 때문이다. 그다음 `is_published` 를 켜고 `stampMilestones` 로 현재 버전 행에 게시 도장을 찍는다. 버전은 행을 더 만들지 않는다. `UNIQUE(article_id, version_number)` 라 같은 번호로 두 줄을 둘 수 없어서, 승인과 게시는 행 추가가 아니라 그 행의 `published_at` 에 날짜를 적는 것이다. 마지막으로 `KnowledgeArticlePublishedEvent` 를 발행하고 끝. 주석이 "실제 RAG 색인은 리스너가 담당"이라고 적어 둔 그대로다.

### 5.2 `KmsArticleEventListener.handleArticlePublished` (190줄) — 커밋 뒤에만

`@TransactionalEventListener(AFTER_COMMIT)` 과 `@Async` 다. 9월 7일 운영 결함이 이 두 애너테이션을 만들었다. 종전 `@EventListener` 는 커밋 전에 돌았고, 색인 스레드가 아직 커밋되지 않은 게시 상태를 읽었다. 2단계 9월 24일의 배치 시작과 같은 모양의 사고가 다른 모듈에서 한 번 더 났던 셈이다. 리스너는 `document_index_status` 를 보고 이미 `COMPLETED` 면 건너뛰고, 아니면 `indexingService.indexDocument(articleId, false)` 를 부른다. 결과가 `COMPLETED` 가 아니면 경고만 남긴다. 게시는 이미 끝났으므로 색인 실패가 게시를 되돌리지 않는다.

같은 파일 101줄의 `handleArticleUpdated` 가 반대 방향이다. 본문이 바뀐 수정 이벤트가 오면 상태가 `COMPLETED` 인 문서만 `UPDATE_REQUIRED` 로 내린다. 4절 2번의 여섯 건이 그렇게 생겼다.

### 5.3 `KmsIndexingServiceImpl.indexDocument` (333줄) — 짧은 트랜잭션과 바깥

2단계 `executeEvaluation` 과 같은 설계다. 먼저 `shortTxTemplate` 안에서 문서 행을 `FOR UPDATE` 로 읽고, 상태를 `PROCESSING` 으로 바꾸고, 본문 · 제목 · 수정 시각 · 지문(제목과 본문의 해시)을 스냅샷으로 떠서 커밋한다. 잠그는 이유가 주석에 있다. 캔버스 승격과 같은 행을 잠가야 본문과 리비전을 같은 시점에 읽는다. 둘을 다른 시점에 읽으면 R1 본문에 R2 리비전이 붙은 교차 세대 벡터가 생긴다.

`index_excluded` 문서는 여기서 갈라진다. 기존 벡터를 지우고 `EXCLUDED` 로 끝낸다. `UPDATE_REQUIRED` 였으면 호출자가 `forceReindex=false` 를 줬어도 강제 재색인으로 올린다. 옛 벡터를 두고 건너뛰면 안 되기 때문이다. 그다음 트랜잭션 밖에서 첨부 파일명과 첨부 본문을 모으고 `rag` 의 `DocumentIndexingService.indexDocument` 를 부른다. 주석 한 줄이 중요하다. "여기서 먼저 삭제하면 임베딩 실패 시 이전 검색 결과가 사라지므로 절대 선삭제하지 않는다."

### 5.4 `DocumentIndexingServiceImpl.indexDocument` (316줄) — 자르고, 재고, 바꿔 끼운다

`htmlToPlainText` (994줄) 가 먼저다. 6월에 생긴 메서드다. 그 전에는 HTML 을 그대로 잘라서 CSS 클래스 이름이 청크를 차지하고 본문은 빠졌다. 어느 보험사 목록이 검색에 0건으로 나오던 원인이 그것이었다. 그다음 `chunkText` (1040줄) 가 500자 조각으로 자르고 50자를 겹친다. 조각마다 임베딩을 묶어서 사이드카에 보낸다. `generateEmbeddingsInBatches` 가 `EmbeddingServiceImpl` (227 · 371줄) 을 거쳐 `POST /embed/batch` 를 부르고, 사이드카는 `upskyy/bge-m3-korean` 으로 1,024개 숫자를 돌려준다. 로컬에서 10503 포트에 떠 있고 `/health` 가 모델 리비전까지 답한다.

저장은 `ON CONFLICT (document_id, field_type, chunk_index)` 의 upsert 다. 같은 문서를 두 스레드가 동시에 색인하다 유일키 위반이 났던 5월 결함이 이 절을 만들었다. 제목은 `TITLE` 필드로 따로 한 줄, 첨부 본문은 `ATTACHMENT` 로 또 따로 들어간다. 그래서 4절 3번에서 한 문서에 필드가 셋이다. 전부 성공하면 원자적으로 옛 청크를 새 청크로 바꾸고, `flowbox` 로 돌아가 `document_index_status` 를 `COMPLETED` 와 `chunk_count` 로 닫는다.

벡터가 바뀌면 `rag_scope_vector_mutation_outbox` 에 한 줄이 남고, 1초마다 도는 `VectorMutationOutboxPoller` 가 그것을 보고 검색 결과 캐시를 비운다. 9월 24일 콜봇 지식베이스를 고친 직후 10분 동안 옛 답이 나오던 일이 이 폴러를 만들었다.

---

## 6. 검색 — `hybridSearch` 한 번 (280줄)

질문 하나가 지나는 단계를 순서대로 적는다.

범위부터 정한다. `resolveStrictRagScope` 가 허용된 문서 번호 집합을 만든다. 호출자가 엄격 범위를 요구했는데 집합이 비면 검색 없이 "근거 없음" 응답이다. 그다음 질의를 다듬는다. 선택적으로 질의 확장을 하고, 연속 중복 토큰을 접고, 임베딩 생성과 형태소 토큰화를 `CompletableFuture` 둘로 동시에 돌린다. 임베딩은 질문 한 문장을 사이드카에 보내 1,024개 숫자로 받는 것이고, 토큰화는 같은 문장을 키워드 색인이 알아듣는 `to_tsquery` 꼴로 바꾸는 것이다.

가중치를 정한다. `resolveAlphaValue` 가 요청의 override → A/B 실험 설정 → 요청의 `alpha` → 용도별 DB 설정 순으로 보고, 아무것도 없으면 0.6 이다. 벡터 6, 키워드 4. 그 가중치와 임베딩으로 캐시를 본다. 유사도 0.985 이상인 최근 질문이 10분 안에 있으면 그 답을 그대로 준다.

SQL 이 돈다. `VectorRepository` 743줄의 문장 하나다.

```
 vector_results   embedding <=> :query 로 가까운 순, 문서당 한 청크, 상위 :limit    ← HNSW, ef_search 는 요청마다
 keyword_results  content_tsvector @@ to_tsquery(:tokens) 를 ts_rank_cd 로, 문서당 한 청크, 상위 :limit
 FULL OUTER JOIN  두 목록을 문서 번호로 합친다
 combined_score = :alphaVector × 1/(60 + vector_rank) + :alphaKeyword × 1/(60 + keyword_rank)
```

이것이 RRF 다. 점수가 아니라 순위를 섞는다. 벡터 쪽 1등은 1/61, 키워드 쪽 1등도 1/61 이고, 양쪽에 다 나온 문서가 위로 올라간다. 60 은 한 쪽 순위가 압도하지 못하게 누르는 상수다. 거리와 ts_rank 값은 그대로 응답에 실려 화면이 보여 주지만 순서는 이 식이 정한다.

리랭커가 다시 순위를 매긴다. 켜져 있으면 상위 열 건(`rerankTopK` 기본 10)의 본문을 사이드카 `/rerank` 로 보내고 `BAAI/bge-reranker-v2-m3` 가 질문과 본문을 한 쌍으로 읽어 점수를 준다. 실패하면 원래 순위로 돌아간다. 9월 15일 커밋이 잡은 결함이 그 자리에 있었다. 본문 창의 문장 경계를 맞추는 코드가 `charAt(-1)` 을 읽어 예외가 났고, 재순위화가 조용히 원래 순위로 강등되고 있었다. 리랭커가 전부를 떨어뜨리면 `recoverWhenRerankerDropsAll` 이 떨어뜨리기 전 후보를 되살린다.

끝으로 감사 로그와 캐시다. `search_queries` 에 한 줄, 성능 지표 한 줄을 비동기로 남기고, 응답을 캐시에 넣는다. 사이드카가 죽어 회로가 열리면 `hybridSearchFallback` 이 `keywordOnlySearch` 로 내려가고 응답에 `degraded` 가 켜진다. 4절 4번의 `KEYWORD` 106건 중 그렇게 내려온 것은 0건이다.

---

## 7. 답변 — 입구 셋

검색 화면 `KmsSearchPage` 하나에 입구가 셋이다. `kms.service.ts` 88줄 주석이 셋을 나란히 적어 두었다.

**AI 답변.** `POST /api/kms/ask` → `KMSRAGService.processNaturalLanguageQuery` (106줄) → `KmsAskEvidenceServiceImpl.search` (43줄). 여기서 4절 노트의 구멍을 막는다. 챕터가 지정되면 `articles.findServingArticleIdsInChapters` 로 서빙 가능한 문서 번호만 모아 `documentIds` 로 넘기고, 집합이 비면 전체 검색으로 넓히지 않고 "근거 없음"으로 끝낸다. 검색 결과는 `StrictRagDecision` 게이트를 지나 `generateAnswer` 로 간다.

**문서 검색.** `POST /api/rag/korean/search` 가 6절을 바로 부른다. 결과는 문서와 청크 목록이고 답변은 없다.

**제목 · 내용 검색.** `GET /api/kms/articles/search` 는 MariaDB 의 `LIKE` 다. 벡터와 무관하고 `servingOnly` 로 거른다. 9월 4일 결함은 이 길에서 났다. 제목이 분해형 한글로 저장되어 있었다. 맥에서 복사한 파일명이 그대로 제목이 됐고, `utf8mb4_unicode_ci` 는 조합형과 분해형을 같은 글자로 보지 않아 8자가 17자 49바이트로 들어가 제목의 단어로 `LIKE` 검색을 해도 0건이었다. RAG 쪽은 `KoreanTextNormalizer` 가 색인과 질의를 NFC 로 맞추고 있어 멀쩡했다. 같은 문서가 AI 답변에는 나오고 제목 검색에는 안 나오던 비대칭의 정체다. 지금은 엔티티의 `@PrePersist` 가 NFC 로 고정한다.

채팅과 평가가 쓰는 네 번째 길이 `KoreanRAGQueryService.processRAGQuery` (82줄) 다. `generateQuery` 가 `RAG_QUERY` 템플릿으로 질문을 검색어로 고쳐 쓰고, `searchDocuments` 가 6절을 부르고, `generateAnswer` 가 `RAG_ANSWER_GENERATION` 템플릿에 문서를 끼워 4단계의 `AiModelFallbackClient` 로 간다. 4단계 이력의 `RAG_QUERY` 106건이 첫 단계의 흔적이다. 질문을 검색어로 바꾸는 데 한 번, 답을 쓰는 데 한 번, 호출이 둘이다.

---

## 8. 다음 단계로 가는 다리

6단계는 `orchestration` 515개와 `agi` 713개다. 이 글에서 이미 두 번 스쳤다. 2단계 평가표에 `workflow_id` 가 있으면 배치가 문항 루프 대신 워크플로우를 돌린다고 했고, 6절의 A/B 실험과 리랭커 검증 잡은 `app.agi.observation` 설정으로 돈다. 4단계에서 오케스트레이터를 가장 많이 부르는 모듈이 `agi` 38곳이었다. 학습 가이드가 6단계를 "필요해지기 전에는 손대지 않는다"고 한 이유는 가장 어렵고 가장 자주 바뀌기 때문이다. 7월 가이드가 적어 둔 두 문서, `claudedocs/agi/AGI_TOOL_ENHANCEMENT_ANALYSIS.md` 와 `claudedocs/orchestration/README.md` 를 먼저 읽는 것이 거기 첫 질문이다.

---

## 9. 함정 모음

1. **검색은 승인 상태를 모른다.** PostgreSQL 에 상태 컬럼이 없다. 게시된 문서만 검색되는 것은 입구 덕이고, 가져오기의 `autoIndex` 는 승인 전에 색인한다. 로컬 74번이 그 사례다.
2. **`UPDATE_REQUIRED` 는 옛 청크로 답하고 있다는 뜻이다.** 본문을 고쳐 저장하면 상태만 바뀌고 재색인은 안 된다. 로컬에 여섯 건, 청크 51개.
3. **"인덱싱 완료" 로그가 완료를 뜻하지 않는다.** 9월 5일 실측에서 승인 직후 자동 색인이 `UPDATE_REQUIRED`, `chunk_count=0` 으로 끝났는데 로그는 완료였다. 리스너가 반환값을 보지 않고 찍는다. 상태 테이블을 믿는다.
4. **재색인 뒤 10분은 캐시가 답한다.** 아웃박스 폴러가 벡터 변경을 보고 비우지만, 폴러가 멈춰 있으면 TTL 까지 옛 결과다. "고쳤는데 그대로"면 `rag_scope_vector_mutation_outbox` 부터.
5. **한 문서에 벡터가 세 종류다.** `TITLE` · `BODY` · `ATTACHMENT`. 청크 수를 셀 때 제목 한 줄이 들어간다.
6. **RRF 는 점수를 섞지 않는다.** 순위를 섞는다. 거리 0.1 짜리와 0.3 짜리가 같은 1/61 이다. 벡터 점수가 높은데 왜 뒤에 있냐는 질문의 답이 이것이다.
7. **리랭커 실패는 조용하다.** 원래 순위로 돌아가고 응답의 리랭커 상태 표시만 바뀐다. 9월 15일 결함처럼 코드 한 줄이 재순위화를 통째로 꺼 놓아도 검색은 멀쩡히 답한다.
8. **`servingOnly` 는 SQL 검색에만 있다.** RAG 경로는 색인 입구와 `ask` 의 문서 집합으로 막는다. 세 입구가 서로 다른 문서 집합을 볼 수 있다.
9. **검색어 정규화에 `KoreanTextNormalizer.normalize()` 를 쓰면 안 된다.** 특수문자를 지워 `2026-09-01` 같은 검색어가 망가진다. NFC 만 하는 `KmsTextNormalization.toNfc()` 를 쓴다.
10. **사이드카 한 대가 셋을 한다.** 임베딩 · 리랭커 · OCR 이 10503 한 포트다. 하나가 느려지면 셋이 같이 느려진다.

---

## 10. 자가진단

1. 문서 한 장이 벡터가 되기까지 지나는 모듈 셋과 각 모듈의 메서드 하나.
2. `knowledge_base_vectors` 의 유일키 세 컬럼과 `field_type` 세 값.
3. `publishArticle` 이 잠그고 다시 읽는 이유.
4. 게시 리스너가 `AFTER_COMMIT` 이어야 하는 이유와 그렇지 않았을 때 났던 일.
5. `UPDATE_REQUIRED` 가 생기는 조건과 그 상태에서 검색이 무엇으로 답하는가.
6. RRF 식과 상수 60 의 역할. 기본 alpha 값.
7. 캐시 적중 조건 둘(유사도 · TTL)과 캐시를 비우는 것.
8. 검색 화면의 입구 셋과 각각이 보는 문서 집합.
9. 9월 4일 제목 검색 0건의 원인과, RAG 는 왜 멀쩡했나.
10. 로컬 74번 문서에 벡터가 있는 이유.

여덟 이상이면 6단계다. 거기부터는 글이 아니라 두 문서로 시작한다.

---

## 부록: 파일 위치 요약

| 관심사 | 파일 | 줄 |
|---|---|---|
| 문서 엔티티 · 서빙 조건 | `kms/entity/KnowledgeArticle.java` · `kms/repository/KnowledgeArticleRepository.java` | 654 · 81 |
| 승인 · 게시 · 도장 | `kms/service/impl/KnowledgeArticleServiceImpl.java` | 1374 · 1564 · 2422 |
| 게시 → 색인 리스너 | `flowbox/event/KmsArticleEventListener.java` | 101 · 190 |
| 색인 접수대 (상태 · 스냅샷 · 선삭제 금지) | `flowbox/service/impl/KmsIndexingServiceImpl.java` | 333 |
| 자르기 · 임베딩 · upsert | `rag/korean/service/impl/DocumentIndexingServiceImpl.java` | 316 · 994 · 1040 |
| 임베딩 클라이언트 (사이드카) | `rag/korean/service/impl/EmbeddingServiceImpl.java` | 227 · 371 |
| 벡터 엔티티 | `rag/korean/entity/KnowledgeBaseVector.java` | 223 |
| 하이브리드 검색 | `rag/korean/service/impl/KoreanSearchServiceImpl.java` | 280 · 3056 |
| RRF SQL | `rag/korean/repository/VectorRepository.java` | 743 |
| 리랭커 | `rag/korean/service/impl/RerankerServiceImpl.java` | 163 |
| 검색 캐시 · 아웃박스 폴러 | `rag/korean/service/impl/RagRetrievalCacheServiceImpl.java` · `outbox/VectorMutationOutboxPoller.java` | 140 · 33 |
| AI 답변 (ask) | `kms/service/KMSRAGService.java` · `kms/service/impl/KmsAskEvidenceServiceImpl.java` | 106 · 43 |
| 채팅 · 평가의 RAG 질의 | `rag/korean/service/KoreanRAGQueryService.java` | 82 |
| AI 전문가 | `kms/service/impl/AIExpertPersonaServiceImpl.java` | 403 · 912 |
| 가져오기의 두 번째 입구 | `kms/controller/DocumentImportController.java` | 341 |
| 사이드카 | `hf-embedding-service/app/main.py` | — |
| 설정 (청크 500/50 · 캐시 0.985/10분 · alpha 0.6) | `application.yml` `rag.korean.*` · PostgreSQL `rrf_alpha_configs` | — |
| 화면 | `web-react/src/pages/kms/search/KmsSearchPage.tsx` · `kms/explorer` · `DocumentManagementPage.tsx` | — |

*문서 끝*
