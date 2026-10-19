import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell, Logo } from "@/components/layout/AppShell";
import { homeFor, useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";
import { LoginPage, RegisterPage } from "@/pages/auth/AuthPages";
import { NotFoundPage } from "@/pages/NotFound";
import { ProfilePage } from "@/pages/Profile";
import { StudentAssessmentsPage } from "@/pages/student/Assessments";
import { StudentDashboard } from "@/pages/student/Dashboard";
import { ResultDetailPage } from "@/pages/student/ResultDetail";
import { ResultsPage } from "@/pages/student/Results";
import { SubmissionsPage } from "@/pages/student/Submissions";
import { TakeAssessmentPage } from "@/pages/student/TakeAssessment";
import { AnalyticsPage } from "@/pages/teacher/Analytics";
import { AssessmentEditorPage } from "@/pages/teacher/AssessmentEditor";
import { AssessmentFormPage } from "@/pages/teacher/AssessmentForm";
import { AssessmentsPage } from "@/pages/teacher/Assessments";
import { TeacherDashboard } from "@/pages/teacher/Dashboard";
import { SubmissionReviewPage } from "@/pages/teacher/SubmissionReview";
import { TeacherSubmissionsPage } from "@/pages/teacher/Submissions";

function FullPageSpinner() {
  return (
    <div className="grid min-h-screen place-items-center bg-slate-25" role="status" aria-label="Loading">
      <span className="margin-pulse"><Logo /></span>
    </div>
  );
}

/** Client-side guard for UX only; every permission is enforced again by the API. */
function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  if (user) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <FullPageSpinner />;
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
      <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />

      <Route path="/teacher" element={<RequireRole role="teacher"><AppShell /></RequireRole>}>
        <Route index element={<TeacherDashboard />} />
        <Route path="assessments" element={<AssessmentsPage />} />
        <Route path="assessments/new" element={<AssessmentFormPage />} />
        <Route path="assessments/:id" element={<AssessmentEditorPage />} />
        <Route path="assessments/:id/edit" element={<AssessmentFormPage />} />
        <Route path="assessments/:id/questions/new" element={<AssessmentEditorPage />} />
        <Route path="assessments/:id/questions/:questionId" element={<AssessmentEditorPage />} />
        <Route path="submissions" element={<TeacherSubmissionsPage />} />
        <Route path="submissions/:id" element={<SubmissionReviewPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>

      <Route path="/student" element={<RequireRole role="student"><AppShell /></RequireRole>}>
        <Route index element={<StudentDashboard />} />
        <Route path="assessments" element={<StudentAssessmentsPage />} />
        <Route path="assessments/:id" element={<TakeAssessmentPage />} />
        <Route path="submissions" element={<SubmissionsPage />} />
        <Route path="results" element={<ResultsPage />} />
        <Route path="results/:id" element={<ResultDetailPage />} />
        <Route path="profile" element={<ProfilePage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
