module.exports = {
  content: ["./report.py", "./src/**/*.py"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Playfair Display", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        // Secondary text stays readable on white/stone and hollow dark cards.
        secondary: { DEFAULT: "#57534e", inverse: "#b9c8c0" },
        hollow: {
          50: "#f0f7f4",
          100: "#dcefe6",
          200: "#bbdfd0",
          300: "#8ec8b1",
          400: "#5eab8d",
          500: "#3d8f72",
          600: "#2e735c",
          700: "#265d4b",
          800: "#214a3d",
          900: "#1d3d33",
          950: "#0d221c",
        },
      },
    },
  },
};
