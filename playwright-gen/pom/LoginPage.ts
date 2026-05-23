import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class LoginPage extends BasePage {

  readonly usernameInput: Locator;

  readonly passwordInput: Locator;

  readonly loginBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.usernameInput = page.locator('#username');

    this.passwordInput = page.locator('#password');

    this.loginBtn = page.locator('#loginBtn');

  }

  async goto() {
    await this.page.goto(`/user/login`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('ログイン');

    await expect(this.page.locator('h1')).toHaveText('ログイン');

    await expect(this.page).toHaveURL(/\/user\/login/);

  }


  async ログイン(username: string, password: string) {



    await this.usernameInput.fill(String(username));



    await this.passwordInput.fill(String(password));



    await this.loginBtn.click();

  }



}
