describe('Offer Letter Flow', () => {
    const email = 'b6005316@gmail.com';

    const password = 'admin@123';
    const loginUrl = 'http://192.168.1.213:8001/nlsatadmissions/login#login';

    before(() => {
        // Clear cookies and local storage before starting
        cy.clearCookies();
        cy.clearLocalStorage();
    });

    it('Logs in, accepts the offer, pays confirmation and admission fees', () => {
        // 1. Login
        cy.visit(loginUrl);
        
        // Wait for login form to be visible and fill credentials
        cy.get('#lp-email', { timeout: 10000 }).should('be.visible').type(email);
        cy.get('#lp-pwd').should('be.visible').type(password);
        cy.get('#lp-login-btn').click();
        
        // Wait for successful login redirect (e.g. to dashboard or offer list)
        cy.url({ timeout: 15000 }).should('not.include', '/login');
        
        // 2. Navigate to Offer Letters list
        cy.visit('http://192.168.1.213:8001/offer_letter/offer-letter-list');
        
        // Wait for offer letters to load and click on the first one
        cy.get('.offer-card', { timeout: 15000 }).should('have.length.greaterThan', 0);
        cy.get('.offer-card').first().click();
        
        // 3. Accept the Offer
        cy.get('body').then($body => {
            if ($body.find('button:contains("Accept Offer")').length > 0) {
                cy.contains('button', 'Accept Offer').click();
                
                // Confirm Acceptance (might require confirming a sweetalert or modal)
                cy.get('.modal').should('be.visible');
                cy.contains('.modal button', 'Confirm').click(); 
                
                // Wait for the status to update to Accepted
                cy.contains('Offer Accepted', { timeout: 10000 }).should('be.visible');
            } else {
                cy.log('Offer already accepted or Accept button not found.');
            }
        });
        
        // 4. Pay Confirmation Fee
        cy.get('body').then($body => {
            if ($body.find('button:contains("Pay Confirmation Fee")').length > 0) {
                cy.contains('button', 'Pay Confirmation Fee').click();
                
                // Modal opens with Proceed to Payment
                cy.get('#payment-modal').should('be.visible');
                cy.contains('button', 'Proceed to Payment').click();
                
                // Wait for Razorpay mock or success API mock
                cy.contains('Payment Completed!', { timeout: 15000 }).should('be.visible');
            } else {
                cy.log('Confirmation Fee already paid or button not found.');
            }
        });

        // Wait for potential reload if payment was successful
        cy.wait(3000); 

        // 5. Pay Admission / Full Fee
        cy.get('body').then($body => {
            if ($body.find('button:contains("Pay Full Fee")').length > 0 || $body.find('button:contains("Pay Admission Fee")').length > 0) {
                let btnText = $body.find('button:contains("Pay Full Fee")').length > 0 ? "Pay Full Fee" : "Pay Admission Fee";
                cy.contains('button', btnText).click();
                
                // Modal opens with Proceed to Payment
                cy.get('#payment-modal').should('be.visible');
                cy.contains('button', 'Proceed to Payment').click();
                
                cy.contains('Payment Completed!', { timeout: 15000 }).should('be.visible');
            } else {
                cy.log('Full Fee already paid or button not found.');
            }
        });
        
        // Final verify that the badge we just added is visible
        cy.contains('Full Fee Paid', { timeout: 10000 }).should('be.visible');
    });

    it('a', function() {
        cy.visit('http://192.168.1.213:8001/nlsatadmissions/login#login')
        
    });
});
