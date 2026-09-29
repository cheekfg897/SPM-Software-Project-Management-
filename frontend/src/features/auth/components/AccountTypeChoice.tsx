import { ROLE } from '@/config/roles'

/** The two kinds of account anyone can create (SCRUM-65 AC3). */
export type AccountType = typeof ROLE.ATTENDEE | typeof ROLE.EVENT_ORGANISER

const ACCOUNT_TYPES: { value: AccountType; label: string; description: string }[] = [
  {
    value: ROLE.ATTENDEE,
    label: 'Attend events',
    description: 'Find events and save your place.',
  },
  {
    value: ROLE.EVENT_ORGANISER,
    label: 'Organise events',
    description: 'Plan events for your organisation with ConnectSphere.',
  },
]

interface AccountTypeChoiceProps {
  value: AccountType
  onChange: (accountType: AccountType) => void
}

/** Attendee or Event Organiser, as two radio cards. The chosen one is sent as `role`. */
export function AccountTypeChoice({ value, onChange }: AccountTypeChoiceProps) {
  return (
    <fieldset>
      <legend className="text-ink mb-2 text-sm font-medium">I want to</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {ACCOUNT_TYPES.map((accountType) => (
          <label
            key={accountType.value}
            className="border-line bg-surface-raised hover:border-flare/50 has-checked:border-flare has-checked:bg-flare/10 has-focus-visible:outline-flare flex cursor-pointer flex-col gap-1 rounded-2xl border p-4 transition has-focus-visible:outline-2"
          >
            <span className="flex items-center gap-2 font-medium">
              <input
                type="radio"
                name="role"
                value={accountType.value}
                checked={value === accountType.value}
                onChange={() => onChange(accountType.value)}
                className="accent-flare"
              />
              {accountType.label}
            </span>
            <span className="text-ink-muted text-sm">{accountType.description}</span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
