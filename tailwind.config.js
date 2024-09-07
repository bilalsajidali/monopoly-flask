/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./templates/**/*.html',  // For Flask HTML templates
    './static/**/*.css',      // If you have other CSS files
    './static/**/*.js', ],
  theme: {
    extend: {},
  },
  plugins: [],
}

