# 은하의 시대 웹 2.5.2

Go/Ebitengine으로 만든 은하의 시대의 웹 포털이다. 네이티브와 WebAssembly는 같은 2.5.2 소스를 사용한다. 전체 71개 진영, 7개 언어, 최대 8세력의 행성 도시경영과 판타지 대륙 정복을 지원한다. SF 캠페인은 47개, 판타지 캠페인은 25개 진영을 허용하며 카오스 데몬은 공통 진영이다.

## 실행과 배포

기존 `.openai/hosting.json`의 프로젝트 ID와 R2 `BUCKET` 바인딩을 유지한다. 사용자의 후속 요청에 따른 공개 사이트다. 첫 화면과 Windows/macOS/Linux 다운로드는 로그인 없이 접근하며, 웹 플레이 및 개인 저장은 ChatGPT 계정 인증을 사용한다. 계정 파일은 서버가 확인한 사용자 ID로 분리한다.

의존성 설치·빌드·관리형 미리보기·발행에는 제공된 Sites 도구를 사용한다. `app/portal.tsx`는 첫 화면과 저장 관리자, `public/game/`은 게임 로더와 저장 브리지, `app/api/`는 인증된 저장 API다.

엔진은 `scripts/engine-assets.py <galactic.wasm> 2.5.2`, 패키지는 `scripts/release-assets.py <native-dist> 2.5.2`으로 갱신한다. 파일을 8MiB 이하 조각으로 나누고 크기와 SHA-256을 기록한다. 브라우저는 완전한 파일을 복원하고 해시를 검증한 뒤 실행 또는 다운로드한다. `wasm_exec.js`는 컴파일러 Go 1.25.14의 동일 파일을 사용한다.

## 저장·언어·그래픽

- 첫 화면에서 고른 언어는 iframe의 `lang`과 Go의 `REALMS_LANG`으로 전달한다. 기존 게임 설정 파일을 덮어쓰지 않는다.
- 실제 게임에는 WebGL2가 필요하다. 첫 화면에 Chrome 그래픽 가속 켜기와 재시작 안내를 제공한다. 사용자 브라우저 설정을 임의로 바꾸지 않는다.
- 전투 저장 `.rsav`, 은하/도시 저장 `gx-*.json`, 대륙/도시 저장 `fc-*.json`은 동일 버전 데스크톱과 교환할 수 있다. IndexedDB, 메모리 사본, 조건부 클라우드 기록을 보존한다.
- 부모 페이지의 바이트 배열은 게임 iframe의 고유 Uint8Array로 복사한다. 이 경계를 없애면 Go의 instanceof 검사 때문에 재실행이 실패한다.
- 매 실행은 새 iframe/Go 인스턴스를 사용한다. 종료된 런타임의 콜백·타이머·오디오·WebGL 자원을 정리한다. 정상 실행 중 오류는 숨기지 않는다.
- 클라우드 충돌 때 미전송 로컬 사본을 보존한다. 삭제는 tombstone으로 기록하며 다른 기기의 오래된 파일이 되살리지 못하게 한다.

## 2.5.2

71개 진영에서 일괄 개편한 유닛 3,552종의 이전 디자인을 복원했다. 개별 수정한 18종은 유지했다.

## 2.5.1

트레숄드-19의 차원탑을 비틀린 금속판과 열린 타원형 고리로 다시 제작했다. 서울에는 눈 없는 인왕산·북악산 산줄기를 배치했다. 하이잘의 놀드랏실·설퍼론 첨탑, 스톰윈드·엘윈 숲, 오그리마·듀로타와 눈 내리는 얼음왕관 성채 전장을 다시 제작했다.

## 2.5.0

71개 진영의 유닛 디자인과 8개 스커미시 전장을 갱신했다. 코버넌트 대학 연구는 보호막 발전기에서 진행한다. 어선 9종과 수송선 11종의 표시 크기를 교정했다.

## 2.4.5

프로토스 거신·전쟁인도자·분노수호자·리버·불멸자·추적자·용기병과 스크린 이레디케이터 헥사포드의 모형을 갱신했다. 리버의 표시 크기는 이전 버전의 두 배다.

## 2.4.4

카오스 데몬을 제외한 판타지 수상 선박, 울나르의 흑요석 신전, 스크린·테란·노드의 네 유닛 모델을 갱신했다.

## 2.4.3

쇼군 집행자와 일반 토르, 스완 토르, 블랙해머, 캠페인 오딘, 타이커스 오딘에 새 게임 모형을 적용했다.

## 2.4.2

쇼군 집행자와 테란 토르를 새로 모델링했다. 세 방향의 상체와 곡검을 갖춘 쇼군 집행자, 팔마다 상하 2연장포와 등 4문 포대를 갖춘 토르를 데스크톱과 웹에서 같은 엔진으로 그린다.

## 2.4.1

도보 유닛과 판타지 비행 유닛의 표시 크기를 조정하고 욱일제국 항공 변신 두 종을 복원했다. 웹과 세 운영체제 배포판은 동일한 게임 소스를 사용한다.

## 2.4.0

웹 엔진의 입력은 `galactic-2.4.0-source.zip`이며 SHA-256은 `5019b5edf0c3f97966276436c36fb8df3c2b44a32b51970eaa7313d6891fdd23`이다. 대륙 캠페인의 해안 항구, 육상·해상 교역, 도시 구역 확장과 판타지·건담 진영의 모형 변경을 포함한다.

홈페이지의 운영체제별 링크는 `/downloads/<manifest의 filename>`이다. 일반 클릭에서는 브라우저가 조각을 합쳐 전체 SHA-256을 검증한다. 직접 URL로 접속하면 서버가 같은 조각을 순서대로 전송한다. 웹에서 공개하는 현재 버전은 `public/releases/manifest.json`과 `public/game/engine.json`으로 확인한다.

## 2.3.0

36·60·84영지와 6종 절차 생성 대륙에서 직접 스커미시로 영지를 점령하고 기존 도시 시스템으로 관리한다. 판타지 건축물과 광역 사업을 연결하고 SF/판타지 캠페인 진영 및 저장 파일을 분리한다. 대륙 저장은 웹의 `continent-fc-*.json`과 네이티브의 `fantasy-campaigns/fc-*.json` 사이에서 교환한다. 전투 비용·결과의 중복 반영을 막고 저장 충돌 시 로컬 사본을 보존한다.

## 2.1.0

건담 3진영, 워크래프트 5진영과 카오스 확장, 52진영 경제·군사·팀 보너스, 일꾼 차량 수리, 테란 건물 비행, 나이트엘프 고대정령 이동, MCV 왕복 변환을 포함한다. 야포는 지면에 계속 사격하며 실제 착탄 **1회**로 범위 안 나무를 제거한다. 그루터기는 저장되며 이동·건설을 막지 않는다. 영웅·단일 제한 유닛은 실제 사망 후 다시 생산할 수 있다.

원작 대응, 적응 방식, 출처와 검증 범위는 별도 네이티브 소스의 `docs/research/` 및 `docs/validation/2.1.0/REVIEW.md`에 기록한다. 기술 등록 검사와 실제 플레이 검증을 혼동하지 않는다.

## 검증

`node node_modules/typescript/bin/tsc --noEmit` 및 `node --test --test-concurrency=1 tests/*.test.mjs`를 사용한다. 테스트 전 아래 Go/WASM fixture를 빌드한다.

```sh
mkdir -p tests/generated
GOOS=js GOARCH=wasm go build -o tests/generated/lifecycle.wasm tests/fixtures/lifecycle.go
GOOS=js GOARCH=wasm go build -o tests/generated/storage-relaunch.wasm tests/fixtures/storage-relaunch/main.go tests/fixtures/storage-relaunch/storage_js.go
GOOS=js GOARCH=wasm go build -o tests/generated/fatal.wasm tests/fixtures/fatal.go
GOOS=js GOARCH=wasm go build -o tests/generated/locale.wasm tests/fixtures/locale.go
```

첫 화면 언어 전환과 그래픽 가속 안내를 실제 브라우저에서 확인했다. 웹 자동 검사는 저장·언어·다운로드·런타임 브리지 검증이며 전체 게임의 GPU 실플레이를 뜻하지 않는다. Linux 실행·화면 검증과 Windows/macOS 교차 컴파일을 구분한다. Windows/macOS 실기기 실행과 macOS 서명·공증은 제공하지 않는다.

### WebAssembly build memory

The 2.4.0 web engine is built from the same native source using Go 1.25.14:

```sh
CGO_ENABLED=0 GOOS=js GOARCH=wasm GOMAXPROCS=1 GOGC=20 GOMEMLIMIT=1536MiB go build -buildvcs=false -mod=vendor -gcflags="realms=-dwarf=false -c=1 -l" -trimpath -ldflags="-s -w" -o galactic.wasm .
```

Package-level function inlining is disabled for all release targets to fit the compiler memory limit. This does not change unit data or simulation rules; actual browser battle performance was not measured in the cloud browser without WebGL 2.
