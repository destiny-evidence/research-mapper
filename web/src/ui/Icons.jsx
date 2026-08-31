// Stroke icons on a 12px grid. Never emoji — these have to recolour and scale.

const stroke = { fill: 'none', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }

export const Tick = ({ colour = '#6f6b63', size = 10 }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" stroke={colour} {...stroke}>
    <path d="M2 6.4 L4.6 9 L10 3" />
  </svg>
)

export const Dot = ({ colour = '#2b2a27', size = 8 }) => (
  <svg width={size} height={size} viewBox="0 0 10 10">
    <circle cx="5" cy="5" r="4" fill={colour} />
  </svg>
)

export const Pause = ({ colour = '#a8551a', size = 8 }) => (
  <svg width={size} height={size} viewBox="0 0 10 10" fill={colour}>
    <rect x="2" y="1.5" width="2.2" height="7" rx="0.5" />
    <rect x="5.8" y="1.5" width="2.2" height="7" rx="0.5" />
  </svg>
)

export const Cross = ({ colour = '#9c3a2f', size = 10 }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" stroke={colour} {...stroke} strokeWidth="1.8">
    <path d="M3.2 3.2 L8.8 8.8 M8.8 3.2 L3.2 8.8" />
  </svg>
)

export const Chevron = ({ up = false, colour = '#86837c', size = 9 }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" stroke={colour} {...stroke} strokeWidth="1.6">
    <path d={up ? 'M3 7.5 L6 4.5 L9 7.5' : 'M3 4.5 L6 7.5 L9 4.5'} />
  </svg>
)

export const Remove = ({ colour = '#a09c94', size = 8 }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" stroke={colour} {...stroke} strokeWidth="1.8">
    <path d="M3 3 L9 9 M9 3 L3 9" />
  </svg>
)

export const Plus = ({ colour = '#86837c', size = 9 }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" stroke={colour} {...stroke} strokeWidth="1.6">
    <path d="M6 2.5 L6 9.5 M2.5 6 L9.5 6" />
  </svg>
)

export const Download = ({ colour = '#86837c', size = 11 }) => (
  <svg width={size} height={size} viewBox="0 0 12 12" stroke={colour} {...stroke} strokeWidth="1.4">
    <path d="M6 1.5 L6 8 M3.5 5.5 L6 8 L8.5 5.5 M2 10.5 L10 10.5" />
  </svg>
)

export const Barrier = ({ size = 16 }) => (
  <svg width={size} height={size * 0.875} viewBox="0 0 16 14" fill="none">
    <path d="M3.5 6 L2.5 13 M12.5 6 L13.5 13" stroke="#a8551a" strokeWidth="1.5" strokeLinecap="round" />
    <rect x="1" y="2.5" width="14" height="4" fill="#a8551a" />
  </svg>
)
