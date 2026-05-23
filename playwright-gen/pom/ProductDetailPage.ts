import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './BasePage';

export class ProductDetailPage extends BasePage {

  readonly dangerBtn: Locator;

  readonly quantityInput: Locator;

  readonly addCartBtn: Locator;

  readonly buyNowBtn: Locator;


  constructor(page: Page) {
    super(page);

    this.dangerBtn = page.locator('.btn-danger');

    this.quantityInput = page.locator('#quantity');

    this.addCartBtn = page.locator('#addCartBtn');

    this.buyNowBtn = page.locator('#buyNowBtn');

  }

  async goto(id: number) {
    await this.page.goto(`/product/detail/${id}`);
  }

  async waitForLoad() {

    await expect(this.page).toHaveTitle(/^商品詳細\ \-/);

    await expect(this.page.locator('h1')).toHaveText('商品詳細');

    await expect(this.page).toHaveURL(/\/product\/detail\/[^\/]+/);

  }


  async 削除() {



    await this.dangerBtn.click();

  }



  async addToCartWithQuantity(quantity: number) {

    await this.quantityInput.fill(String(quantity));

    await this.addCartBtn.click();
  }


  async buyNow(quantity: number) {

    await this.quantityInput.fill(String(quantity));

    await this.buyNowBtn.click();
  }


}
