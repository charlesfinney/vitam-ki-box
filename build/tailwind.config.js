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
        muted: '#74748a',
        slate: '#424257',
        focus: '#4d65cb',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: {
        ui: '20px',
      },
    },
  },
  plugins: [],
};
