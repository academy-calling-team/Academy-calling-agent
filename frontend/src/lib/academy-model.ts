export type AccountType = 'parent' | 'academy';
export interface Preference {
  subject_code: string;
  grade_code: string;
  level_code: string | null;
}
export interface CallWindow {
  days: number[];
  start: string;
  end: string;
}
export interface AcademyProfile {
  name: string;
  phone: string;
  region: string;
  address: string;
  classes: Preference[];
  windows: CallWindow[];
  updated_at?: string;
}
export const days = ['월', '화', '수', '목', '금', '토', '일'];
export function emptyProfile(): AcademyProfile {
  return { name: '', phone: '', region: '', address: '', classes: [], windows: [{ days: [], start: '14:00', end: '18:00' }] };
}
export function validateProfile(profile: AcademyProfile): string {
  if (!profile.name.trim() || profile.name.trim().length > 80) return '학원명을 80자 이내로 입력해 주세요.';
  if (!/^[+\d()\s-]{7,25}$/.test(profile.phone) || profile.phone.replace(/\D/g, '').length < 7) return '전화번호를 확인해 주세요.';
  if (!profile.region) return '지역을 선택해 주세요.';
  if (profile.classes.length > 50 || new Set(profile.classes.map((p) => JSON.stringify(p))).size !== profile.classes.length) return '중복된 선호 대상을 삭제해 주세요. 최대 50개까지 설정할 수 있습니다.';
  if (!profile.windows.length) return '전화 응대 가능 시간을 추가해 주세요.';
  const ranges: { day: number; start: string; end: string }[] = [];
  for (const window of profile.windows) {
    if (!window.days.length || !window.start || !window.end || window.start >= window.end) return '요일을 선택하고 종료 시간을 시작 시간보다 늦게 설정해 주세요.';
    for (const day of window.days) {
      if (ranges.some((r) => r.day === day && r.start < window.end && window.start < r.end)) return '같은 요일의 응대 시간이 겹치지 않도록 설정해 주세요.';
      ranges.push({ day, start: window.start, end: window.end });
    }
  }
  if (ranges.length > 50) return '요일별 응대 시간은 최대 50개까지 설정할 수 있습니다.';
  return '';
}
