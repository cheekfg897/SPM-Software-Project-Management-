/**
 * Business time: the backend sends every date-time in it (ADR-0009), and dates are shown in
 * it whatever the viewer's own time zone. Matches the backend's APP_TIMEZONE default.
 */
export const BUSINESS_TIME_ZONE = 'Asia/Singapore'

/**
 * Business time is a fixed UTC+8 all year, which is what lets a date-time input's value be
 * turned into an ISO date-time with an offset by appending this.
 */
export const BUSINESS_UTC_OFFSET = '+08:00'
