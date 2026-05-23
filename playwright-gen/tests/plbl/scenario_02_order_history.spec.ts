import { test, expect, Page } from '@playwright/test';
import { LoginPage }         from '../../pom/LoginPage';
import { ProductDetailPage } from '../../pom/ProductDetailPage';
import { OrderListPage }     from '../../pom/OrderListPage';
import { OrderDetailPage }   from '../../pom/OrderDetailPage';

const TEST_USER = { username: 'user1', password: 'dummy' };

async function login(page: Page): Promise<void> {
  const loginPage = new LoginPage(page);
  await loginPage.goto();
  await loginPage.waitForLoad();
  await loginPage.ログイン(TEST_USER.username, TEST_USER.password);
  await page.waitForURL(/\/product\/list/);
}

// 商品詳細から今すぐ購入し、注文詳細ページに遷移する共通操作
async function buyNowProduct(
  page: Page,
  productId: number,
  quantity = 1
): Promise<string | undefined> {
  const detail = new ProductDetailPage(page);
  await detail.goto(productId);
  await detail.waitForLoad();

  const navPromise = page.waitForURL(/\/order\/detail\//);
  await detail.buyNow(quantity);
  await navPromise;

  // 遷移後のURLから orderId を取得して返す
  return page.url().match(/\/order\/detail\/(\d+)/)?.[1];
}

test.describe('シナリオ2: 注文履歴確認・キャンセル・受け取り完了', () => {

  test('注文後に注文履歴一覧に注文が表示される', async ({ page }) => {
    await login(page);
    await buyNowProduct(page, 1);  // ノートPC × 1

    await page.goto('/order/list');
    const orderList = new OrderListPage(page);
    await orderList.waitForLoad();

    // 1件以上の注文が表示されること
    // 注意: テストを繰り返し実行すると累積するため toHaveCount(1) は使用しない
    await expect(page.locator('#order-list tbody tr')).not.toHaveCount(0);
    // 直近の注文が PENDING ステータスで表示されること
    await expect(page.locator('#order-list tbody tr').first()).toContainText('PENDING');
  });

  test('注文一覧から詳細リンクをクリックして注文詳細ページへ遷移できる', async ({ page }) => {
    await login(page);
    await buyNowProduct(page, 2);  // スマートフォン × 1

    await page.goto('/order/list');
    const orderList = new OrderListPage(page);
    await orderList.waitForLoad();

    // 最初の「詳細」リンクをクリック
    await page.locator('a', { hasText: '詳細' }).first().click();

    const orderDetail = new OrderDetailPage(page);
    await orderDetail.waitForLoad();
    await expect(page).toHaveURL(/\/order\/detail\/\d+/);
    // 注文明細が1行以上あること
    await expect(page.locator('#itemsTable tbody tr')).not.toHaveCount(0);
  });

  test('PENDING注文をキャンセルするとキャンセルボタンが非表示になる', async ({ page }) => {
    await login(page);
    await buyNowProduct(page, 1);  // ノートPC × 1

    await page.goto('/order/list');
    const orderList = new OrderListPage(page);
    await orderList.waitForLoad();

    // キャンセル対象の注文IDを取得しておく（先頭行を対象とする）
    const firstRow = page.locator('#order-list tbody tr').first();
    const orderId = (await firstRow.locator('td').nth(0).textContent())?.trim();

    // キャンセルボタンのconfirmダイアログを自動承認する
    // 複数の注文が存在するため先頭行（最新注文）のキャンセルボタンを直接指定する
    page.once('dialog', dialog => dialog.accept());
    await page.locator('#order-list tbody tr').first().locator('.btn-danger').click();

    // キャンセル後は /order/list にリダイレクトされる
    await orderList.waitForLoad();
    await expect(page).toHaveURL(/\/order\/list/);

    // キャンセルした注文行の .btn-danger（キャンセルボタン）が非表示になること
    // PENDING 以外のステータスではボタンが JSP テンプレートで出力されない
    if (orderId) {
      // :text-is() で注文ID列の完全一致に絞り込む（日付等に含まれる部分一致を除外）
      const targetRow = page.locator(`#order-list tbody tr:has(td:first-child:text-is("${orderId}"))`);
      await expect(targetRow.locator('.btn-danger')).toHaveCount(0);
    }
  });

  test('注文詳細で受け取り完了を実行するとステータスが COMPLETED になる', async ({ page }) => {
    await login(page);
    await buyNowProduct(page, 1);  // buyNow後は /order/detail/{id} にいる

    const orderDetail = new OrderDetailPage(page);
    await orderDetail.waitForLoad();
    // 購入直後は PENDING であること
    await expect(page.locator('#orderStatus')).toHaveText('PENDING');
    await expect(page.locator('#completeBtn')).toBeVisible();

    // completeOrder(): confirm() ダイアログ承認 → AJAX POST /order/api/complete/{id}
    //   → JS が DOM を直接更新（#orderStatus = 'COMPLETED', #completeBtn disabled）
    page.once('dialog', dialog => dialog.accept());
    const responsePromise = page.waitForResponse(
      resp => resp.url().includes('/order/api/complete/') && resp.status() === 200
    );
    await orderDetail.completeOrder();
    await responsePromise;

    // ページリロード不要（JS が DOM を直接更新する）
    await expect(page.locator('#orderStatus')).toHaveText('COMPLETED');
    await expect(page.locator('#completeBtn')).toBeDisabled();
  });
});
