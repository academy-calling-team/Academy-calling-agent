import { api } from './api';
import type { AcademyProfile, Preference } from './academy-model';

interface AcademyResponse {
  academy_id: string;
  name: string;
  phone: string;
  region: string;
  address: string;
  classes: Preference[];
  call_hours: { day_of_week: number; start_time: string; end_time: string }[];
  version: number;
  updated_at: string;
}

function profileFromResponse(data: AcademyResponse): AcademyProfile {
  return {
    ...data,
    classes: data.classes.map(({ subject_code, grade_code, level_code }) => ({ subject_code, grade_code, level_code })),
    windows: data.call_hours.map((hour) => ({
      days: [hour.day_of_week], start: hour.start_time.slice(0, 5), end: hour.end_time.slice(0, 5),
    })),
  };
}

export async function getAcademy(): Promise<AcademyProfile> {
  return profileFromResponse(await api<AcademyResponse>('/api/my-academy'));
}

export async function putAcademy(profile: AcademyProfile, create: boolean): Promise<AcademyProfile> {
  const { name, phone, region, address, classes, version } = profile;
  const call_hours = profile.windows.flatMap((window) => window.days.map((day_of_week) => ({
    day_of_week, start_time: window.start, end_time: window.end,
  })));
  const data = await api<AcademyResponse>('/api/my-academy', {
    method: create ? 'POST' : 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, phone, region, address, classes, call_hours, ...(create ? {} : { version }) }),
  });
  return profileFromResponse(data);
}
