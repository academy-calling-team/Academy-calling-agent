import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import Shell from './components/Shell';
import { AuthProvider } from './hooks/useAuth';
import { ToastProvider } from './hooks/useToast';
import OverviewPage from './pages/OverviewPage';
import NewInquiryPage from './pages/NewInquiryPage';
import TasksPage from './pages/TasksPage';
import DetailPage from './pages/DetailPage';
import AuthPage from './pages/AuthPage';

function HashBridge() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const raw = window.location.hash.replace(/^#/, '');
    if (!raw || raw.startsWith('/')) return;
    const path = '/' + raw.replace(/^\//, '');
    if (path !== location.pathname) {
      navigate(path + window.location.search, { replace: true });
    }
  }, [location, navigate]);
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
