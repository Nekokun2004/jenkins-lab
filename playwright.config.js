module.exports = {
  testDir: './e2e',
  reporter: [
    ['junit', { outputFile: 'playwright-report/junit.xml' }],
    ['html', { outputFolder: 'playwright-report/html', open: 'never' }],
  ],
  use: {
    baseURL: process.env.API_BASE_URL || 'http://localhost:8081',
  },
};
