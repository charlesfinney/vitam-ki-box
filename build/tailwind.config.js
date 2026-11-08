/** Vita Concierge site — tokens from UI-design.html (see decisions-and-prelaunch.md, item 8) */
module.exports = {
  // Scan the sources the generator builds from, so classes in any language are kept.
  content: ['./templates/**/*.html', './content/**/*.html'],
  theme: {
    extend: {
      colors: {
        ink: '#000000',
        paper: '#ffffff',
        line: '#e6e6f0',
        muted: '#606075', // was #74748a; darker so grey text passes WCAG AA on lavender (4.9:1) and white (6.1:1)
        slate: '#424257',
        focus: '#4d65cb',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        display: ['Unbounded', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        ui: '20px',
      },
    },
  },
  plugins: [],
};
