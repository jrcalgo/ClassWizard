import {test,expect} from '@playwright/test';

test('saved session restores and unsaved changes cannot generate stale results',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Explore a demo'}).click();
 await expect(page.locator('.alert[role="status"]')).toContainText('Synthetic student loaded');
 await page.reload();
 await expect(page.locator('.sidebar-footer')).toContainText('Private session active');
 await page.getByRole('button',{name:'Academic profile',exact:false}).first().click();
 await expect(page.getByRole('textbox',{name:'Completed courses and grades'})).toContainText('ITSC 1212');
 await page.getByRole('spinbutton',{name:'Current GPA'}).fill('3.1');
 await page.getByRole('button',{name:'Recommendations',exact:false}).first().click();
 await expect(page.getByRole('button',{name:'Find my next courses'})).toBeDisabled();
 await page.getByRole('button',{name:'Academic profile',exact:false}).first().click();
 await page.getByRole('button',{name:'Save reviewed profile'}).click();
 await expect(page.locator('.alert[role="status"]')).toContainText('Academic state reviewed and saved');
 await page.getByRole('button',{name:'Recommendations',exact:false}).first().click();
 await expect(page.getByRole('button',{name:'Find my next courses'})).toBeEnabled();
 await page.getByRole('button',{name:'End session & delete data'}).click();
});

test('variable-credit entries save canonical course codes and numeric hours',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Explore a demo'}).click();
 await expect(page.locator('.alert[role="status"]')).toContainText('Synthetic student loaded');
 await page.getByText('Departmental confirmations and variable-credit courses',{exact:true}).click();
 await page.getByRole('textbox',{name:'Variable-credit selections'}).fill('binf3900, 3');
 await page.getByRole('spinbutton',{name:'Current GPA'}).click();
 await page.getByRole('button',{name:'Career & preferences',exact:false}).first().click();
 await page.getByRole('button',{name:'Save preferences'}).click();
 await expect(page.locator('.alert[role="status"]')).toContainText('Planning preferences saved');
 const response=await page.request.get('/api/v1/session');
 expect((await response.json()).preferences.variable_credits).toEqual({'BINF 3900':3});
 await page.getByRole('button',{name:'End session & delete data'}).click();
});
