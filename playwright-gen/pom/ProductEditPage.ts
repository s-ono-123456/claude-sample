import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class ProductEditPage extends BasePage {

  readonly nameInput: Locator;

  readonly priceInput: Locator;

  readonly stockInput: Locator;


  constructor(page: Page) {
    super(page);

    this.nameInput = page.locator('#name');

    this.priceInput = page.locator('#price');

    this.stockInput = page.locator('#stock');

  }

  async goto(id: number) {
    await this.page.goto(`/product/edit/${id}`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('商品編集新規商品登録');

    await expect(this.page.locator('h1')).toHaveText('商品編集新規商品登録');

    await expect(this.page).toHaveURL(/\/product\/edit\/[^\/]+/);

  }



}
