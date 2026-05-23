import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class UserRegisterPage extends BasePage {

  readonly usernameInput: Locator;

  readonly emailInput: Locator;

  readonly registerBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.usernameInput = page.locator('#username');

    this.emailInput = page.locator('#email');

    this.registerBtn = page.locator('#registerBtn');

  }

  async goto() {
    await this.page.goto(`/user/register`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('新規ユーザー登録');

    await expect(this.page.locator('h1')).toHaveText('新規ユーザー登録');

    await expect(this.page).toHaveURL(/\/user\/register/);

  }


  async 登録(username: string, email: string) {



    await this.usernameInput.fill(String(username));



    await this.emailInput.fill(String(email));



    await this.registerBtn.click();

  }



}
