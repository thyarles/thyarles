const { defineConfig } = require("cypress");

module.exports = defineConfig({
  defaultBrowser: 'chrome',
  viewportHeight: 900,
  viewportWidth: 1400,
  e2e: {
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
  },
});
