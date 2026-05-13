import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import DashboardPage from './pages/DashboardPage'
import ExchangePage from './pages/ExchangePage'
import CurrencyDetailPage from './pages/CurrencyDetailPage'
import UpgradePage from './pages/UpgradePage'

/**
 * Root application component.
 * Wraps the entire app in AuthProvider so all components can access auth state.
 *
 * Routes:
 *   /login                    — Login form
 *   /register                 — Registration form
 *   /forgot-password          — Forgot password flow (3 steps)
 *   /dashboard                — Protected dashboard (requires authentication)
 *   /exchange                 — Currency exchange & top-up (task 6.2)
 *   /currency/:currencyCode   — Currency detail page with tour list (task 7.3)
 *   /upgrade                  — Premium upgrade page (task 8.2)
 *   /                         — Redirects to /dashboard
 */
function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardPage />
              </ProtectedRoute>
            }
          />
          {/* Task 6.2 — Currency Exchange & Top-Up */}
          <Route
            path="/exchange"
            element={
              <ProtectedRoute>
                <ExchangePage />
              </ProtectedRoute>
            }
          />
          {/* Task 7.3 — Currency Detail Page with Tour List */}
          <Route
            path="/currency/:currencyCode"
            element={
              <ProtectedRoute>
                <CurrencyDetailPage />
              </ProtectedRoute>
            }
          />
          {/* Task 8.2 — Premium Upgrade Page */}
          <Route
            path="/upgrade"
            element={
              <ProtectedRoute>
                <UpgradePage />
              </ProtectedRoute>
            }
          />
          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
