"""Server policy for live calls to approved mobile numbers.

These are server settings, never request parameters. The voice worker applies
its own independent destination/enable checks as a second gate.
"""
import os
import re
from dataclasses import dataclass

TEST_ACADEMY_ID = 'team8-real-call-test'

def phone(value):
    value = re.sub(r'[\s()-]', '', value or '')
    if re.fullmatch(r'010[0-9]{8}', value):
        value = '+82' + value[1:]
    return value if re.fullmatch(r'\+8210[0-9]{8}', value) else None


def allowed_phones(value):
    entries = [number.strip() for number in value.split(',')]
    numbers = [phone(number) for number in entries]
    return frozenset(numbers) if all(numbers) else frozenset()

@dataclass(frozen=True)
class RealTestPolicy:
    enabled: bool = False
    academy_id: str = TEST_ACADEMY_ID
    allowed_to: str = ''
    inquirer_id: str = ''
    mode: str = 'legacy'

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('REAL_CALLS_ENABLED') == '1', TEST_ACADEMY_ID,
                   os.environ.get('REAL_CALL_ALLOWED_TO', ''),
                   os.environ.get('REAL_TEST_INQUIRER_ID', ''), os.environ.get('REAL_CALL_MODE', 'legacy'))

    def allows_academy(self, academy):
        if not self.enabled or academy['is_mock']:
            return False
        number = phone(academy['phone'])
        if self.mode == 'allowlist':
            return number is not None and number in allowed_phones(self.allowed_to)
        return bool(self.mode == 'legacy' and self.inquirer_id and academy['id'] == self.academy_id
                    and number and number == phone(self.allowed_to))

    def permits(self, academy, owner):
        return bool(owner and self.allows_academy(academy)
                    and (self.mode == 'allowlist' or owner == self.inquirer_id))

    def public(self, academy):
        is_test = academy['id'] == self.academy_id and not academy['is_mock']
        ready = self.allows_academy(academy)
        if academy['is_mock']:
            notice = ''
        elif ready:
            notice = '실제 전화 1회 · 자동 재발신 없음'
            if self.mode == 'legacy':
                notice = '지정 시험 계정만 ' + notice
        elif not self.enabled:
            notice = '발신 불가 · 현재 실제 전화 발신이 꺼져 있습니다.'
        elif self.mode == 'allowlist':
            notice = '발신 불가 · 등록된 번호가 실제 발신 허용 목록에 없습니다.'
        else:
            notice = '발신 불가 · 지정 시험 학원과 시험 계정을 확인해 주세요.'
        return dict(is_test=is_test, can_submit=bool(academy['is_mock'] or ready),
                    max_attempts=1 if not academy['is_mock'] else None,
                    notice=notice)
