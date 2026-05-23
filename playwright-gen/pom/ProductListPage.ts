import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class ProductListPage extends BasePage {

  readonly categorySelectInput: Locator;

  readonly searchBtn: Locator;

  readonly placeOrderBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.categorySelectInput = page.locator('#categorySelect');

    this.searchBtn = page.locator('#searchBtn');

    this.placeOrderBtn = page.locator('#placeOrderBtn');

  }

  async goto() {
    await this.page.goto(`/product/list`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle('商品一覧');

    await expect(this.page.locator('h1')).toHaveText('商品一覧');

    await expect(this.page).toHaveURL(/\/product\/list/);

  }


  async 検索(categorySelect: string) {



    await this.categorySelectInput.selectOption(String(categorySelect));



    await this.searchBtn.click();

  }



  async placeOrder() {

    await this.placeOrderBtn.click();
  }


}
