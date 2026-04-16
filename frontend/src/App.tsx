import { Routes, Route, Navigate } from 'react-router-dom'
import { ToastContainer } from 'react-toastify'
import 'react-toastify/dist/ReactToastify.min.css'
import { AuthContext } from './stores/authStore'
import { useAuthProvider } from './hooks/useAuthProvider'
import ProtectedRoute from './components/ProtectedRoute'
import MainLayout from './components/Layout/MainLayout'
import LoginPage from './pages/Login/LoginPage'
import ChangePasswordPage from './pages/ChangePassword/ChangePasswordPage'
import YouTubePage from './pages/YouTube/YouTubePage'
import ConverterPage from './pages/Converter/ConverterPage'
import ImageProcessorPage from './pages/ImageProcessor/ImageProcessorPage'
import AdminPage from './pages/Admin/AdminPage'

export default function App() {
  const auth = useAuthProvider()

  return (
    <AuthContext.Provider value={auth}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />

        <Route
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route
            path="/youtube"
            element={
              <ProtectedRoute requiredPermission="youtube">
                <YouTubePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/converter"
            element={
              <ProtectedRoute requiredPermission="converter">
                <ConverterPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/image"
            element={
              <ProtectedRoute requiredPermission="image">
                <ImageProcessorPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute adminOnly>
                <AdminPage />
              </ProtectedRoute>
            }
          />
        </Route>

        <Route path="*" element={<Navigate to="/youtube" replace />} />
      </Routes>

      <ToastContainer
        position="bottom-right"
        autoClose={4000}
        hideProgressBar={false}
        newestOnTop
        closeOnClick
        pauseOnHover
        theme="dark"
      />
    </AuthContext.Provider>
  )
}
