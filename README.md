# stay-stranger.github.io

개발하다 만난 오류를 증상이 아니라 원인까지 따라간 기록.

https://stay-stranger.github.io

## 구조

```
index.html                 홈 — 카테고리별 글 목록
assets/css/site.css        홈 공용 스타일
assets/css/post.css        글 공용 스타일
advisor/                   어드바이저 — 코드베이스 학습 기록 (index.html 이 시리즈 목차)
ops-log/                   운영기록 카테고리
error-handling/            오류처리 카테고리
  two-oracle-drivers.html  두 개의 OracleDriver (ORA-28040)
.nojekyll                  Jekyll 빌드 없이 정적 파일 그대로 서빙
```

각 글은 스타일을 포함한 단일 HTML 파일이라 그 자체로 열립니다.

## 글 추가하기

1. 카테고리 폴더에 HTML 파일을 하나 넣는다.
2. `index.html`의 해당 카테고리에 `.post` 카드를 추가하고 개수를 갱신한다.
