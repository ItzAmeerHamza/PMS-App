import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1c2430",
        muted: "#5c6b7a",
        line: "#e4ebf2",
        teal: "#0f6e6b",
        panel: "#f6f8fb",
      },
    },
  },
  plugins: [],
};

export default config;
