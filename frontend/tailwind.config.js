/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#06060A',
        charcoal: '#121219',
        graphite: '#1C1C26',
        line: '#2A2A38',
        fg: '#ECEBF5',
        muted: '#8A88A0',
        violet: '#7C5CFF',
        azure: '#3B82F6',
        ok: '#34D399',
        bad: '#F87171',
      },
      fontFamily: {
        sans: ['Manrope', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      borderRadius: { xl2: '1.25rem' },
    },
  },
  plugins: [],
}
