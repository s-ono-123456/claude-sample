import { test, expect, Page } from '@playwright/test';
import { LoginPage }         from '../../pom/LoginPage';
import { ProductListPage }   from '../../pom/ProductListPage';
import { ProductDetailPage } from '../../pom/ProductDetailPage';
import { OrderDetailPage }   from '../../pom/OrderDetailPage';

// data.sql に登録済みのテストユーザー
// UserServiceImpl はパスワードを照合しないため任意のパスワードでログイン可能
const TEST_USER = { username: 'user1', password: 'dummy' };

async function login(page: Page): Promise<void> {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.waitForLoad();
  await loginPage.ログイン(TEST_USER.username, TEST_USER.password);
  await page.waitForURL(/\/product\/list/);
}

test.describe('シナリオ1: 商品一覧 → 商品詳細 → 購入', () => {

  test('ログイン後に商品一覧が表示される', async ({ page }) => {
    await login(page);

    const products = new ProductListPage(page);
    await products.waitForLoad();

    // data.sql に登録された6商品がすべて表示されること
    await expect(page.locator('#product-list tbody tr')).toHaveCount(6);
  });

  test('カテゴリ絞り込みを実行できる', async ({ page }) => {
    await login(page);

    const products = new ProductListPage(page);
    await products.waitForLoad();

    // 検索() は selectOption() を使うため <select> に正しく機能する
    await products.検索('electronics');
    await products.waitForLoad();

    await expect(page).toHaveURL(/[?&]category=electronics/);
    // data.sql のカテゴリ値が英語統一されたため電子機器2件が絞り込まれる
    await expect(page.locator('#product-list tbody tr')).toHaveCount(2);
    await expect(page.locator('#product-list tbody')).toContainText('ノートPC');
    await expect(page.locator('#product-list tbody')).toContainText('スマートフォン');
  });

  test('商品名リンクから商品詳細ページへ遷移できる', async ({ page }) => {
    await login(page);

    // 一覧の最初の行の商品名リンクをクリック（ノートPC → /product/detail/1）
    await page.locator('#product-list tbody tr').first().locator('td a').first().click();

    const detail = new ProductDetailPage(page);
    await detail.waitForLoad();  // toHaveTitle(/^商品詳細 -/) で確認
    await expect(page).toHaveURL(/\/product\/detail\/\d+/);
    await expect(page.locator('#product-detail h2')).toContainText('ノートPC');
  });

  test('商品詳細から今すぐ購入すると注文詳細ページへ遷移する', async ({ page }) => {
    await login(page);

    const detail = new ProductDetailPage(page);
    await detail.goto(1);
    await detail.waitForLoad();

    // buyNow(quantity):
    //   1. #quantity に数量を fill
    //   2. #buyNowBtn をクリック → JS buyNow(productId) 実行
    //   3. AJAX GET /product/api/detail/1 → AJAX POST /order/place → window.location.href へリダイレクト
    const navPromise = page.waitForURL(/\/order\/detail\//);
    await detail.buyNow(1);
    await navPromise;

    const orderDetail = new OrderDetailPage(page);
    await orderDetail.waitForLoad();
    await expect(page.locator('#orderStatus')).toHaveText('PENDING');
    // 注文明細が1行あること（ノートPC × 1）
    await expect(page.locator('#itemsTable tbody tr')).toHaveCount(1);
  });

  test('商品一覧でカートに追加して注文する（placeOrder）', async ({ page }) => {
    await login(page);

    const products = new ProductListPage(page);
    await products.waitForLoad();

    // .btn-cart クリック → JS addToCart → AJAX → cart[] 更新 → #cart-panel 表示
    // waitForResponse ではなく DOM 変化（#cart-panel 可視化）で完了を確認する
    // （AJAX レスポンス受信後に JS コールバックが実行されるまでの非同期ギャップを回避）
    await page.locator('.btn-cart').first().click();
    await page.locator('#cart-panel').waitFor({ state: 'visible' });

    // placeOrder(): cart[] から AJAX POST /order/place
    //   → 成功後 setTimeout(1500ms) → window.location.href でリダイレクト
    //   → waitForURL は 1500ms より十分長いタイムアウトを指定する
    const navPromise = page.waitForURL(/\/order\/detail\//, { timeout: 10_000 });
    await products.placeOrder();
    await navPromise;

    const orderDetail = new OrderDetailPage(page);
    await orderDetail.waitForLoad();
    await expect(page.locator('#orderStatus')).toHaveText('PENDING');
  });
});
