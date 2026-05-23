import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class OrderListPage extends BasePage {

  readonly dangerBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.dangerBtn = page.locator('.btn-danger');

  }

  async goto() {
    await this.page.goto(`/order/list`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('注文履歴');

    await expect(this.page.locator('h1')).toHaveText('注文履歴');

    await expect(this.page).toHaveURL(/\/order\/list/);

  }


  async キャンセル() {



    await this.dangerBtn.click();

  }



}
