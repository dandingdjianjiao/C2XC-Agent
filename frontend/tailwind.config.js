/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--c2xc-bg)',
        surface: 'var(--c2xc-surface)',
        fg: 'var(--c2xc-fg)',
        muted: 'var(--c2xc-muted)',
        border: 'var(--c2xc-border)',
        accent: 'var(--c2xc-accent)',
        'accent-fg': 'var(--c2xc-accent-fg)',
        danger: 'var(--c2xc-danger)',
        warn: 'var(--c2xc-warn)',
        success: 'var(--c2xc-success)',
      },
    },
  },
  plugins: [],
}
