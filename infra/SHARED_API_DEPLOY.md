# 공동 개발 API 배포

기본 주소: https://team8-api.3.35.222.227.sslip.io/shared

- 명세: `/docs`, 상태: `/ready`, 실행 커밋: `/version`.
- GitHub Actions의 `Shared API checks and deploy`에서 검사·배포 결과를 확인한다.
- `main`의 backend/voice/frontend/infra/배포 workflow 변경을 검사한 후 공동 API·큐·음성 목업 워커를 배포한다. PR은 검사만 한다. Actions에서 main으로 수동 재실행도 가능하다.
- **프론트는 각 PC에서 실행한다. 이 workflow는 프론트 코드를 검사하지만 프론트 사이트를 AWS에 게시하지 않는다.** 프론트 변경을 받으려면 git pull과 로컬 서버 재시작이 필요하다.
- 문서만 바뀌면 자동 배포하지 않는다. 테스트 실패 시 배포하지 않고 기존 서비스를 유지한다.
- 신규 가입에는 `terms_agreed: true`가 필수이며 실제 체크박스 선택을 전달한다. 기존 계정의 NULL 동의 시각을 임의로 채우지 않는다. 기존 프론트는 먼저 최신 코드를 받아야 신규 가입할 수 있다.

## 구성과 권한

`shared-api-autodeploy.cfn.json`은 GitHub OIDC 제공자, main 한정 역할, 전용 SSM 문서만 생성한다. 새 EC2/RDS/로드밸런서/유료 GitHub runner는 추가하지 않는다. AWS 키나 DB 암호를 GitHub에 저장하지 않는다.

이 저장소는 공개 저장소이므로 EC2가 검사된 커밋의 소스를 GitHub에서 직접 내려받는다. 저장소가 비공개로 바뀌면 별도 소스 전달 경로가 필요하다.

호스트의 `/opt/team8-shared-api/deploy/deploy.py`가 release controller다. 최초 설치는 운영자가 수행한다. 초기 Python 기반 이미지 `team8-fe-dev-api:06e07b1`은 공유 API 이미지 빌드의 기반이므로 삭제하지 않는다.

배포 전 새 이미지 빌드·DB 컬럼 호환성·임시 API 준비 상태 검사와 DB 백업을 수행한다. DB 스키마를 자동 변경하지 않는다. 마이그레이션이 필요한 코드는 먼저 검토·적용해야 하며, 컬럼이 없으면 기존 API를 내리지 않고 배포를 중단한다.

큐를 멈추고 진행 중인 목업 통화가 끝나면 API·워커·큐를 교체한다. 교체 중 짧은 API 중단이 있을 수 있다. 기존 MySQL/Redis·워커 접수 볼륨과 다른 API는 유지한다. 교체 실패 시 이전 컨테이너를 복구한다. 백업 파일과 런타임 설정은 root 전용이며 Git/Actions 로그로 출력하지 않는다.

## 운영 확인

2026-10-19 변경: Actions는 일회용 MySQL·Redis로 백엔드 전체 테스트를 실행한다. 실통화 시험 설정은 [시험 절차](../docs/collaboration/실통화_시험.md)에 따라 별도로 입력·활성화한다. 배포만으로 발신을 활성화하지 않는다.

1. Actions의 검사와 deploy job이 모두 성공했는지 확인한다.
2. `/version`의 커밋과 main 커밋을 비교한다.
3. `/docs`의 회원가입에 terms_agreed가 필수로 표시되는지 확인한다.
4. 신규 테스트 계정의 동의/거부/누락, 로그인, 문의 1건의 목업 왕복, DB의 terms_agreed_at 저장을 확인한다.

SSM 배포 출력에 release와 백업 위치가 남는다. 현재 배포 기록은 `/opt/team8-shared-api/current-release.json`이며 이전 컨테이너 한 세대를 유지한다. 자동 배포를 멈추려면 GitHub Actions에서 workflow를 비활성화한다. 기존 서비스는 계속 실행된다.
