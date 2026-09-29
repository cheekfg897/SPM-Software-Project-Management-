import { AuthCard } from '../components/AuthCard'
import { LoginForm } from '../components/LoginForm'
import { SignedOutOnly } from '../components/SignedOutOnly'

/**
 * Log in for Event Coordinators, Venue Staff and Technical Support Staff (SCRUM-6). There is
 * no sign-up: staff accounts are created with `flask create-staff-user` (ADR-0023).
 */
export function StaffLoginPage() {
  return (
    <SignedOutOnly>
      <AuthCard
        title="Staff log in"
        description="For Event Coordinators, Venue Staff and Technical Support Staff."
        footer={
          <p>Staff accounts are set up by ConnectSphere. Ask your team lead if you need one.</p>
        }
      >
        <LoginForm />
      </AuthCard>
    </SignedOutOnly>
  )
}
