import { useCallback, useEffect, useRef, useState } from 'react';
import { api, getSessionEpoch } from '../lib/api';
import type { Academy, CatalogOptions, InquiryDetail, InquiryListItem } from '../lib/inquiry-model';

export function useCatalog(enabled = true) {
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [options, setOptions] = useState<CatalogOptions | null>(null);
  const [academies, setAcademies] = useState<Academy[]>([]);
  const [error, setError] = useState('');
  const loadingRef = useRef(false);

  const load = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    const epoch = getSessionEpoch();
    setState('loading');
    setError('');
    try {
      const [opts, acs] = await Promise.all([
        api<CatalogOptions>('/api/options'),
        api<Academy[]>('/api/academies'),
      ]);
      if (epoch !== getSessionEpoch()) return;
      setOptions(opts);
      setAcademies(acs);
      setState('ready');
    } catch (err) {
      if (epoch !== getSessionEpoch()) return;
      setState('error');
      setError((err as Error).message);
    } finally {
      loadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (enabled && state === 'idle') void load();
  }, [enabled, state, load]);

  return { state, options, academies, error, reload: load };
}

export function useInquiryList() {
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [rows, setRows] = useState<InquiryListItem[]>([]);
  const [details, setDetails] = useState<Record<string, InquiryDetail>>({});
  const [error, setError] = useState('');
  const [offset, setOffset] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const versionRef = useRef(0);

  const load = useCallback(async () => {
    const version = ++versionRef.current;
    const epoch = getSessionEpoch();
    setState('loading');
    setError('');
    try {
      const listOffset = offset;
      const nextRows = await api<InquiryListItem[]>(
        `/api/inquiries?limit=10&offset=${listOffset}`,
      );
      if (epoch !== getSessionEpoch() || version !== versionRef.current) return;
      setRows(nextRows);
      setHasNext(nextRows.length === 10);
      const results = await Promise.allSettled(
        nextRows.map((t) => api<InquiryDetail>('/api/inquiries/' + encodeURIComponent(t.inquiry_id))),
      );
      if (epoch !== getSessionEpoch() || version !== versionRef.current) return;
      const map: Record<string, InquiryDetail> = {};
      let failed = 0;
      results.forEach((r, i) => {
        if (r.status === 'fulfilled') map[nextRows[i].inquiry_id] = r.value;
        else failed += 1;
      });
      setDetails(map);
      setState('ready');
      setUpdated(new Date().toISOString());
      setError(failed ? '일부 상담 정보를 불러오지 못했습니다. 다시 시도해 주세요.' : '');
    } catch (err) {
      if (epoch !== getSessionEpoch() || version !== versionRef.current) return;
      setState('error');
      setError((err as Error).message);
    }
  }, [offset]);

  useEffect(() => {
    void load();
  }, [load]);

  return {
    state,
    rows,
    details,
    error,
    offset,
    setOffset,
    hasNext,
    updated,
    reload: load,
  };
}

export function useInquiryDetail(id: string | undefined) {
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle');
  const [detail, setDetail] = useState<InquiryDetail | null>(null);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState<string | null>(null);
  const versionRef = useRef(0);

  const load = useCallback(async () => {
    if (!id) return;
    const version = ++versionRef.current;
    const epoch = getSessionEpoch();
    setState('loading');
    setError('');
    try {
      const data = await api<InquiryDetail>('/api/inquiries/' + encodeURIComponent(id));
      if (epoch !== getSessionEpoch() || version !== versionRef.current) return;
      setDetail(data);
      setState('ready');
      setUpdated(new Date().toISOString());
    } catch (err) {
      if (epoch !== getSessionEpoch() || version !== versionRef.current) return;
      setState('error');
      setError((err as Error).message);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  return { state, detail, error, updated, reload: load };
}
