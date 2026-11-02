import React from 'react'
const paths = {
  dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  employees: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M22 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
  structure: 'M9 2h6v6H9z M2 16h6v6H2z M16 16h6v6h-6z M12 8v4 M5 16v-4h14v4',
  vacancies: 'M9 6V3h6v3 M3 6h18v15H3z M3 11c5 4 13 4 18 0 M10 12h4v4h-4z',
  matching: 'M5 4h14v16H5z M8 9l2 2 5-5 M8 16h8',
  analytics: 'M4 3v18h17 M8 16v-5 M13 16V7 M18 16V3',
  assistant: 'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  methodology: 'M4 5h16 M4 12h16 M4 19h16 M8 2v6 M16 9v6 M10 16v6',
  catalogs: 'M4 3h6v18H4z M14 3h6v18h-6z M4 8h6 M14 8h6',
  audit: 'M3 12a9 9 0 1 0 3-6.7 M3 3v5h5 M12 7v5l3 2',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  shield: 'M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6z M8 12l3 3 5-6',
}
export default function Icon({ name, size = 20 }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.dashboard} /></svg>
}
