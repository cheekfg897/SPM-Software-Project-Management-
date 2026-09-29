import type { ButtonHTMLAttributes } from 'react'
import { Link } from 'react-router'
import type { LinkProps } from 'react-router'

import { Spinner } from './Spinner'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'

const BASE_CLASSES =
  'inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60'

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-gradient-to-r from-corona via-flare to-ember text-void hover:brightness-110',
  secondary: 'border border-line bg-surface-raised text-ink hover:border-flare/60',
  ghost: 'text-ink-muted hover:text-ink',
}

function buttonClasses(variant: ButtonVariant, className = ''): string {
  return `${BASE_CLASSES} ${VARIANT_CLASSES[variant]} ${className}`
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  /** Disables the button and shows a spinner while a request is in flight. */
  isPending?: boolean
}

export function Button({
  variant = 'primary',
  isPending = false,
  type = 'button',
  className,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses(variant, className)}
      disabled={disabled === true || isPending}
      aria-busy={isPending}
      {...rest}
    >
      {isPending && <Spinner />}
      {children}
    </button>
  )
}

interface ButtonLinkProps extends LinkProps {
  variant?: ButtonVariant
}

/** A link that looks like a button, for navigation rather than actions. */
export function ButtonLink({ variant = 'primary', className, ...rest }: ButtonLinkProps) {
  return <Link className={buttonClasses(variant, className)} {...rest} />
}
