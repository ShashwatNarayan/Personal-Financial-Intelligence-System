/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js"
  ],
  theme: {
    extend: {
      // Ported from the inline `tailwind.config` previously consumed by the
      // Tailwind Play CDN in newDashboard.html / transactions.html, so the
      // compiled stylesheet reproduces every named-token utility the markup uses.
      "colors": {
        "secondary": "#88d899",
        "background": "#101510",
        "secondary-container": "#01602e",
        "inverse-surface": "#dfe4dc",
        "tertiary-fixed": "#ffd9e0",
        "inverse-on-surface": "#2d322c",
        "primary-container": "#5bae6d",
        "tertiary": "#ffb1c3",
        "surface-variant": "#313631",
        "error": "#ffb4ab",
        "on-primary": "#003916",
        "outline-variant": "#3f493f",
        "on-error-container": "#ffdad6",
        "error-container": "#93000a",
        "surface-bright": "#363a35",
        "primary-fixed": "#a0f6ae",
        "on-tertiary": "#5e112e",
        "primary-fixed-dim": "#84d993",
        "on-primary-container": "#003e19",
        "surface-container-high": "#262b26",
        "on-secondary": "#003918",
        "on-primary-fixed": "#00210a",
        "tertiary-container": "#e57d99",
        "tertiary-fixed-dim": "#ffb1c3",
        "surface-container-highest": "#313631",
        "secondary-fixed-dim": "#88d899",
        "surface-container": "#1c211c",
        "on-tertiary-container": "#641632",
        "on-surface-variant": "#bfc9bc",
        "on-background": "#dfe4dc",
        "surface-tint": "#84d993",
        "primary": "#84d993",
        "on-secondary-fixed-variant": "#005226",
        "surface-container-low": "#181d18",
        "outline": "#899488",
        "on-secondary-fixed": "#00210c",
        "surface-container-lowest": "#0b0f0b",
        "on-surface": "#dfe4dc",
        "on-secondary-container": "#87d899",
        "surface": "#101510",
        "on-tertiary-fixed-variant": "#7b2944",
        "on-error": "#690005",
        "on-tertiary-fixed": "#3f0019",
        "surface-dim": "#101510",
        "secondary-fixed": "#a3f5b3",
        "inverse-primary": "#126d34",
        "on-primary-fixed-variant": "#005323"
      },
      "borderRadius": {
        "DEFAULT": "0.25rem",
        "lg": "0.5rem",
        "xl": "0.75rem",
        "full": "9999px"
      },
      "spacing": {
        "margin-mobile": "16px",
        "gutter": "16px",
        "lg": "24px",
        "md": "16px",
        "max-width": "1280px",
        "sm": "8px",
        "xl": "40px",
        "base": "4px",
        "xs": "4px",
        "margin-desktop": "32px"
      },
      "fontFamily": {
        "headline-lg-mobile": ["Inter"],
        "data-mono": ["JetBrains Mono"],
        "body-md": ["Inter"],
        "body-lg": ["Inter"],
        "label-caps": ["Inter"],
        "headline-lg": ["Inter"],
        "headline-md": ["Inter"]
      },
      "fontSize": {
        "headline-lg-mobile": ["24px", {"lineHeight":"1.2","letterSpacing":"-0.01em","fontWeight":"600"}],
        "data-mono": ["14px", {"lineHeight":"1.5","letterSpacing":"-0.01em","fontWeight":"400"}],
        "body-md": ["14px", {"lineHeight":"1.5","letterSpacing":"0","fontWeight":"400"}],
        "body-lg": ["16px", {"lineHeight":"1.6","letterSpacing":"0","fontWeight":"400"}],
        "label-caps": ["12px", {"lineHeight":"1","letterSpacing":"0.05em","fontWeight":"600"}],
        "headline-lg": ["32px", {"lineHeight":"1.2","letterSpacing":"-0.02em","fontWeight":"600"}],
        "headline-md": ["20px", {"lineHeight":"1.4","letterSpacing":"-0.01em","fontWeight":"500"}]
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries')
  ],
}
