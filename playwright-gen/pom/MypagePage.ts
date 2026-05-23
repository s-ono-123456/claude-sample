import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class MypagePage extends BasePage {

  readonly emailInput: Locator;

  readonly updateBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.emailInput = page.locator('#email');

    this.updateBtn = page.locator('#updateBtn');

  }

  async goto() {
    await this.page.goto(`/user/mypage`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('マイページ');

    await expect(this.page.locator('h1')).toHaveText('マイページ');

    await expect(this.page).toHaveURL(/\/user\/mypage/);

  }


  async 更新(email: string) {



    await this.emailInput.fill(String(email));



    await this.updateBtn.click();

  }



}
