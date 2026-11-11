import { emptyProfile, type AcademyProfile, type AccountType } from './academy-model';

const prefix = 'hakwon:academy-preview:v1:';
export interface PreviewUser { userId: string; displayName: string; registered: boolean; accountType: AccountType }
export function previewUser(): PreviewUser | null {
  const raw = localStorage.getItem(prefix + 'session');
  return raw ? JSON.parse(raw) as PreviewUser : null;
}
export function setPreviewUser(user: PreviewUser | null) {
  if (user) localStorage.setItem(prefix + 'session', JSON.stringify(user));
  else localStorage.removeItem(prefix + 'session');
}
export function registerPreview(name: string, accountType: AccountType) {
  if (localStorage.getItem(prefix + 'account:' + name)) throw new Error('이미 사용 중인 아이디입니다.');
  localStorage.setItem(prefix + 'account:' + name, JSON.stringify({ userId: name, displayName: name, registered: true, accountType }));
}
export function loginPreview(name: string) {
  const raw = localStorage.getItem(prefix + 'account:' + name);
  if (!raw) throw new Error('미리보기 계정을 먼저 등록해 주세요.');
  setPreviewUser(JSON.parse(raw) as PreviewUser);
}
export function readAcademy(userId: string): AcademyProfile | null {
  const raw = localStorage.getItem(prefix + 'profile:' + userId);
  return raw ? JSON.parse(raw) as AcademyProfile : null;
}
export function saveAcademy(userId: string, profile: AcademyProfile) {
  const saved = { ...profile, name: profile.name.trim(), phone: profile.phone.trim(), address: profile.address.trim(), updated_at: new Date().toISOString() };
  localStorage.setItem(prefix + 'profile:' + userId, JSON.stringify(saved));
  return saved;
}
export function selectScenario(kind: 'parent' | 'new' | 'existing') {
  const userId = 'demo-' + kind;
  if (kind === 'new') localStorage.removeItem(prefix + 'profile:' + userId);
  if (kind === 'existing' && !readAcademy(userId)) saveAcademy(userId, { ...emptyProfile(), name: '침산 배움학원', phone: '053-000-0000', region: '대구 북구 침산동', classes: [{ subject_code: 'MATH', grade_code: 'E3', level_code: null }], windows: [{ days: [0, 1, 2, 3, 4], start: '14:00', end: '18:00' }] });
  setPreviewUser({ userId, displayName: kind === 'parent' ? '학부모 미리보기' : '학원 미리보기', registered: true, accountType: kind === 'parent' ? 'parent' : 'academy' });
}
