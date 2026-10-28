context('Applicant Form Dropdown Filters', () => {
    before(() => {
        cy.login();
        cy.visit('/nlsatadmissions/application-form/new');
    });

    it('Filters state options based on selected country', () => {
        // Assume 'INDIA' is the default country. Wait for form to load.
        cy.get('[data-fieldname="country"] input').should('have.value', 'INDIA');

        // Click state dropdown to see options
        cy.get('[data-fieldname="state"] input').focus().click();

        // Let the awesomplete load the queries
        cy.get('[data-fieldname="state"] ul[role="listbox"]').should('be.visible');

        // Type 'TAM' to filter
        cy.get('[data-fieldname="state"] input').type('TAM');
        
        // Assert that 'TAMIL NADU' is one of the options
        cy.get('[data-fieldname="state"] ul[role="listbox"]')
          .contains('TAMIL NADU')
          .should('exist');
    });

    it('Filters city options based on selected state', () => {
        // Select TAMIL NADU
        cy.get('[data-fieldname="state"] input').clear().type('TAMIL NADU').type('{enter}');
        
        // Ensure state is selected
        cy.get('[data-fieldname="state"] input').should('have.value', 'TAMIL NADU');

        // Now focus on city and type 'CH'
        cy.get('[data-fieldname="city"] input').focus().click().clear().type('CH');
        
        // Assert that Chennai is listed
        cy.get('[data-fieldname="city"] ul[role="listbox"]')
          .contains('CHENNAI', { matchCase: false })
          .should('exist');
          
        // Ensure that a city not in Tamil Nadu (e.g. BENGALURU) is NOT listed
        cy.get('[data-fieldname="city"] ul[role="listbox"]')
          .contains('BENGALURU', { matchCase: false })
          .should('not.exist');
    });
});
