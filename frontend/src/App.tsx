import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useMemo } from 'react';
import AcademyPage from './pages/AcademyPage';
import Shell from './components/Shell';
import { AuthProvider } from './hooks/useAuth';
import { ToastProvider } from './hooks/useToast';
import OverviewPage from './pages/OverviewPage';
import NewInquiryPage from './pages/NewInquiryPage';
import TasksPage from './pages/TasksPage';
import DetailPage from './pages/DetailPage';
import AuthPage from './pages/AuthPage';

function HashBridge() {
  const preview = useMemo(() => new URLSearchParams(window.location.search).get('preview') === 'mock', []);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (preview && !new URLSearchParams(location.search).has('preview')) {
      navigate(location.pathname + '?preview=mock' + location.hash, { replace: true });
    }
    const raw = window.location.hash.replace(/^#/, '');
    if (!raw || raw.startsWith('/')) return;
    const path = '/' + raw.replace(/^\//, '');
    if (path !== location.pathname) {
      navigate(path + window.location.search, { replace: true });
    }
  }, [location, navigate, preview]);
  return null;
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <HashBridge />
        <Shell>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/overview" element={<Navigate to="/" replace />} />
            <Route path="/academy/register" element={<AcademyPage />} />
            <Route path="/academy/manage" element={<AcademyPage />} />
            <Route path="/new" element={<NewInquiryPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/detail/:id" element={<DetailPage />} />
            <Route path="/login" element={<AuthPage mode="login" />} />
            <Route path="/register" element={<AuthPage mode="register" />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
      </ToastProvider>
    </AuthProvider>
  );
}
