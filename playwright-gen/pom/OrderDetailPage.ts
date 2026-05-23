import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class OrderDetailPage extends BasePage {

  readonly completeBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.completeBtn = page.locator('#completeBtn');

  }

  async goto(id: number) {
    await this.page.goto(`/order/detail/${id}`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('注文詳細');

    await expect(this.page.locator('h1')).toHaveText('注文詳細');

    await expect(this.page).toHaveURL(/\/order\/detail\/[^\/]+/);

  }



  async completeOrder() {

    await this.completeBtn.click();
  }


}
