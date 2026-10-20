import {test,expect} from '@playwright/test';
test('synthetic academic profile to recommendations and valid plan',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'A clearer path forward.'})).toBeVisible();
 await page.getByRole('button',{name:'Explore a demo'}).click();
 await expect(page.locator('.alert[role="status"]')).toContainText('Synthetic student loaded');
 await page.getByRole('button',{name:'Recommendations',exact:false}).first().click();
 await page.getByRole('button',{name:'Find my next courses'}).click();
 await expect(page.locator('.course').first()).toBeVisible();
 await page.getByRole('button',{name:'Semester plan',exact:false}).first().click();
 await page.getByRole('button',{name:'Generate semester plan'}).click();
 await expect(page.locator('.alert')).toContainText('Constraint-valid proposal');
 await expect(page.locator('.semester-grid .panel').first()).toBeVisible();
 await page.getByRole('button',{name:'End session & delete data'}).click();
 await expect(page.locator('.alert[role="status"]')).toContainText('data has been deleted');
});
test('course explorer works at mobile width',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await page.getByRole('button',{name:'Course explorer',exact:false}).click();
 await page.getByRole('textbox',{name:'Search courses'}).fill('ITSC 1212');
 await page.getByRole('button',{name:'Search',exact:false}).click();
 await expect(page.locator('summary').first()).toContainText('ITSC 1212');
});
