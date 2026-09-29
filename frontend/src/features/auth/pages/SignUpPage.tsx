import { Link } from 'react-router'

import { ROUTES } from '@/config/routes'

import { AuthCard } from '../components/AuthCard'
import { SignedOutOnly } from '../components/SignedOutOnly'
import { SignUpForm } from '../components/SignUpForm'

/** Sign up as an Event Organiser or Attendee (SCRUM-65). Staff can't sign up (ADR-0023). */
export function SignUpPage() {
  return (
    <SignedOutOnly>
      <AuthCard
        title="Create your account"
        description="Join ConnectSphere to find events, or to plan your own."
        footer={
          <p>
            Already have an account?{' '}
            <Link to={ROUTES.LOGIN} className="text-flare font-medium hover:underline">
              Log in instead
            </Link>
          </p>
        }
      >
        <SignUpForm />
      </AuthCard>
    </SignedOutOnly>
  )
}
