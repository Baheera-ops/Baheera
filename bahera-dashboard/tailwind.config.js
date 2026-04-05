/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#eef2ff", 100: "#e0e7ff", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca" },
        score: {
          hot: { bg: "#dcfce7", text: "#166534", border: "#86efac" },
          warm: { bg: "#dbeafe", text: "#1e40af", border: "#93c5fd" },
          nurture: { bg: "#fef9c3", text: "#854d0e", border: "#fde047" },
          cold: { bg: "#f3f4f6", text: "#374151", border: "#d1d5db" },
        },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
