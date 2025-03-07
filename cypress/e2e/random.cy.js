describe('Open URLs and fetch API data', () => {
  // Function to generate a random time between 5 and 30 seconds
  function randomDelay() {
    return Math.floor(Math.random() * (30000 - 5000 + 1)) + 1000;
  }

  it('should open STF', () => {
    cy.visit('https://portal.stf.jus.br');
    cy.wait(randomDelay());
  });

  it('should open STJ', () => {
    cy.visit('https://processo.stj.jus.br');
    cy.wait(randomDelay());
  });

  it('should get SF1 data', () => {
    cy.request('https://sistemas.trf1.jus.br/pgp-api/api/local/JFDF/processo/1023891-47.2023.4.01.3400?ordem=1&max=10&offset=0')
      .then((response) => {
        cy.writeFile('cypress/fixtures/SF1.json', response.body);
      });
    cy.wait(randomDelay());
  });

  it('should get CD1 data', () => {
    cy.request('https://sistemas.trf1.jus.br/pgp-api/api/local/JFDF/processo/1026558-69.2024.4.01.3400?ordem=1&max=10&offset=0')
      .then((response) => {
        cy.writeFile('cypress/fixtures/CD1.json', response.body);
      });
  });
});
