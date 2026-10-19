"""Opt-in policy for one academy, recipient and existing test account.

These are server settings, never request parameters. The voice worker applies
its own independent destination/enable checks as a second gate.
"""
import os
import re
from dataclasses import dataclass

TEST_ACADEMY_ID = 'team8-real-call-test'

def phone(value):
    value = re.sub(r'[\s()-]', '', value or '')
    if value.startswith('010') and re.fullmatch(r'010\d{8}', value):
        value = '+82' + value[1:]
    return value if re.fullmatch(r'\+8210\d{8}', value) else None

@dataclass(frozen=True)
class RealTestPolicy:
    enabled: bool = False
    academy_id: str = TEST_ACADEMY_ID
    allowed_to: str = ''
    inquirer_id: str = ''

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('REAL_CALLS_ENABLED') == '1', TEST_ACADEMY_ID,
                   os.environ.get('REAL_CALL_ALLOWED_TO', ''),
                   os.environ.get('REAL_TEST_INQUIRER_ID', ''))

    def permits(self, academy, owner):
        return bool(self.enabled and self.inquirer_id and owner == self.inquirer_id
                    and academy['id'] == self.academy_id and not academy['is_mock']
                    and phone(self.allowed_to) and phone(academy['phone']) == phone(self.allowed_to))

    def public(self, academy):
        is_test = academy['id'] == self.academy_id and not academy['is_mock']
        ready = self.permits(academy, self.inquirer_id)
        return dict(is_test=is_test, can_submit=bool(academy['is_mock'] or ready),
                    max_attempts=1 if not academy['is_mock'] else None,
                    notice=('지정 시험 계정만 실제 전화 1회 · 자동 재발신 없음' if ready else
                            '실통화 시험 준비 중 · 수신자와 서버 설정 확인 후 접수 가능')
                           if is_test else '')
