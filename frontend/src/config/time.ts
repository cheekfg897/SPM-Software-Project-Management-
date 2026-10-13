/**
 * Business time: the backend sends every date-time in it (ADR-0009), and dates are shown in
 * it whatever the viewer's own time zone. Matches the backend's APP_TIMEZONE default.
 */
export const BUSINESS_TIME_ZONE = 'Asia/Singapore'

/** How dates and times are written for people: "Thu, 12 Nov", "9:00 am". */
export const DISPLAY_LOCALE = 'en-SG'
