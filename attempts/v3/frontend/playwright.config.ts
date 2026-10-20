import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',timeout:90000,expect:{timeout:15000},use:{baseURL:process.env.BASE_URL||'http://localhost:8083',headless:true},reporter:'list'});
