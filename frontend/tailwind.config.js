/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        accent: '#00FF88',
        terminal: {
          bg: '#0a0d0e',
          panel: '#11161a',
          border: '#1e2a31',
          text: '#c6d4d9',
          muted: '#6b7b82',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
};
