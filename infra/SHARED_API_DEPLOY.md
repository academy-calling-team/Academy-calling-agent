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

## 배포 성공·실패 이력

SSM 문서는 독립된 `deploy-observability.py`를 먼저 실행하고 그 안에서 기존 `deploy.py`를 호출한다. 운영자가 **wrapper를 먼저 설치·검증한 뒤** CloudFormation으로 SSM 문서를 갱신한다. `UpdateMethod: NewVersion`으로 기존 문서를 유지하며 새 기본 버전을 만든다. 설치 시 root 소유 700, 이력 폴더 700·JSON 파일 600을 적용한다. GitHub OIDC 역할과 보안그룹·DNS 설정을 변경할 필요가 없다.

기록 위치는 `/opt/team8-shared-api/deployment-history/배포ID.json`이다. 성공·실패·중단 상태, 시작/종료 시각(UTC), 대상 커밋, GitHub 실행 링크, 단계, 알려진 오류 종류·errno, 배포 전후 DNS/내부·공개 ready·version, 컨테이너 실행/OOM/재시작 횟수와 서버 메모리·디스크·부하를 저장한다. `after`는 배포 프로그램이 반환한 **뒤**의 관측이므로 실패 시 복구 이후 상태일 수 있다. 단계 이벤트는 시각과 단계만 저장하며 단계마다 서버 전체를 측정하지 않는다. 실패 원인과 종료 후 DNS 정상 결과가 동시에 남을 수 있다.

```bash
# 서버 접속 후 최근 30건: 한국시간, 성공/실패, 커밋, 배포ID
sudo python3 /opt/team8-shared-api/deploy/deploy-observability.py history

# 목록의 배포ID를 복사해 상세 보기
sudo python3 /opt/team8-shared-api/deploy/deploy-observability.py show 배포ID

# 현재 상태를 읽기만 하기: 앱 재시작·발신 없음
sudo python3 /opt/team8-shared-api/deploy/deploy-observability.py status
```

다음 배포가 시작될 때 90일 초과·최신 500건 밖의 오래된 이력을 정리한다(1시간 이내 진행 건 보호). 원시 앱 로그·환경변수·계정/문의/통화 식별자·녹음·전사·HTTP 응답 원문은 이력에 저장하지 않는다. 예외 메시지와 자식 프로그램 원문 출력도 저장/전달하지 않고 허용된 오류 종류만 추출한다. 기존 이미지 빌드 로그·DB 백업의 수명 정책은 별개다.

GitHub에서는 실행 페이지의 Summary와 Artifacts의 `deployment-result-실행ID-회차`를 확인한다. 검사가 실패해 서버 배포가 시작되지 않은 경우도 별도 report job이 결과를 저장한다. SSM 실행이 완료돼 응답을 받은 경우 `server-deployment-실행ID-회차`도 90일 보관한다. 서버 이력과 Actions 결과는 서로 다른 범위다. PR의 deploy skipped는 배포 실패가 아니다. 조직/저장소의 보관 한도·GitHub 저장 용량 정책이 우선한다.

서버가 꺼지거나 프로세스가 강제 종료되면 완료 스냅샷은 남지 않을 수 있다. 최초 `running` 파일은 남으며 30분 이상 갱신이 없으면 history에 `unfinished (check SSM)`로 표시한다. 서버 디스크가 소실되면 로컬 이력도 소실된다. 이 기능은 배포 시점의 진단 기록이며, 상시 서버 모니터링이나 과거 장애 원인 소급 확정을 제공하지 않는다. 기존 공개 readiness의 재시도/롤백 정책은 별도 변경이다.

되돌릴 때는 SSM 문서를 이전 기본 버전으로 돌려 기존 `deploy.py` 직접 호출을 복원한다. 실행 중인 배포를 먼저 확인하고, 보관 이력은 삭제하지 않는다. CloudFormation 템플릿도 같은 상태로 맞춰 이후 변경이 되살리지 않게 한다.
