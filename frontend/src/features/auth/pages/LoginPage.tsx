import { Link } from 'react-router'

import { ROUTES } from '@/config/routes'

import { AuthCard } from '../components/AuthCard'
import { LoginForm } from '../components/LoginForm'
import { SignedOutOnly } from '../components/SignedOutOnly'

/** Log in for Event Organisers and Attendees (SCRUM-6). */
export function LoginPage() {
  return (
    <SignedOutOnly>
      <AuthCard
        title="Log in"
        description="Welcome back. Pick up where you left off with your events."
        footer={
          <p>
            New to ConnectSphere?{' '}
            <Link to={ROUTES.SIGN_UP} className="text-flare font-medium hover:underline">
              Create an account
            </Link>
          </p>
        }
      >
        <LoginForm />
      </AuthCard>
    </SignedOutOnly>
  )
}
