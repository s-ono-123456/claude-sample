package com.example.testsampleapp.service;

import com.example.testsampleapp.dao.CustomerDao;
import com.example.testsampleapp.dao.OrderDao;
import com.example.testsampleapp.dao.OrderItemDao;
import com.example.testsampleapp.dao.ProductDao;
import com.example.testsampleapp.model.Coupon;
import com.example.testsampleapp.model.Customer;
import com.example.testsampleapp.model.Order;
import com.example.testsampleapp.model.OrderCalculationResult;
import com.example.testsampleapp.model.OrderItem;
import com.example.testsampleapp.model.OrderSearchCriteria;
import com.example.testsampleapp.model.Product;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.util.List;

/**
 * 注文金額計算サービス。
 *
 * calculateOrderAmount は、テストケース・テストデータ作成の練習素材として
 * 意図的に分割せず1メソッドへ集約した、多数の分岐・ループを持つ長大メソッドである。
 * 各分岐の対応関係は docs/design.md の「金額計算ロジック仕様」表を参照すること。
 *
 * メソッド内の calculationLog は、各STEPの分岐結果と中間値を記録するための
 * 検証用ログである。最終的な金額計算には影響しないが、複雑な分岐を通過する際に
 * どの条件が成立したかをテスト時に目視確認できるようにするために保持している。
 */
@Service
public class OrderCalculationServiceImpl implements OrderCalculationService {

    @Autowired
    private OrderDao orderDao;

    @Autowired
    private OrderItemDao orderItemDao;

    @Autowired
    private CustomerDao customerDao;

    @Autowired
    private ProductDao productDao;

    @Override
    public List<Order> searchOrders(OrderSearchCriteria criteria) {
        return orderDao.search(criteria);
    }

    @Override
    public OrderCalculationResult calculateOrderAmount(Integer orderId) {

        // calculateOrderAmount 全体を通じて、どの分岐をどの条件で通過したかを
        // 記録するための検証ログ。テストケース設計時に分岐網羅の確認に使う。
        StringBuilder calculationLog = new StringBuilder();
        calculationLog.append("=== calculateOrderAmount orderId=").append(orderId).append(" ===\n");

        // ===================================================================
        // STEP 1: Order / Customer / OrderItem一覧 / Product群の取得
        // ---------------------------------------------------------------
        // 目的: 注文計算に必要な4種類のエンティティ（注文・顧客・明細・商品）を
        //       揃え、以降のSTEPで参照する派生値（注文月など）を準備する。
        // テスト観点: 存在しない orderId / customerId を渡した場合に
        //             IllegalArgumentException が発生することを確認する。
        // ===================================================================
        Order order = orderDao.findById(orderId);
        if (order == null) {
            // 分岐(1): 注文が存在しない場合は処理を継続できないため例外とする
            calculationLog.append("STEP1: order not found. orderId=").append(orderId).append("\n");
            throw new IllegalArgumentException("注文が見つかりません: orderId=" + orderId);
        }
        calculationLog.append("STEP1: order found. orderId=").append(order.getId()).append("\n");

        Customer customer = customerDao.findById(order.getCustomerId());
        if (customer == null) {
            // 分岐(1-b): 注文に紐づく顧客が存在しない場合も同様に処理を継続できない
            calculationLog.append("STEP1: customer not found. customerId=").append(order.getCustomerId()).append("\n");
            throw new IllegalArgumentException("顧客が見つかりません: customerId=" + order.getCustomerId());
        }
        calculationLog.append("STEP1: customer found. memberRank=").append(customer.getMemberRank())
                .append(", region=").append(customer.getRegion())
                .append(", birthMonth=").append(customer.getBirthMonth())
                .append(", firstOrderFlag=").append(customer.getFirstOrderFlag()).append("\n");

        List<OrderItem> orderItems = orderItemDao.findByOrderId(orderId);
        order.setItems(orderItems);
        calculationLog.append("STEP1: orderItems loaded. count=").append(orderItems.size()).append("\n");

        LocalDate orderDate = order.getOrderDate();
        int orderMonth = orderDate.getMonthValue();
        calculationLog.append("STEP1: orderDate=").append(orderDate)
                .append(", orderMonth=").append(orderMonth).append("\n");

        // ===================================================================
        // STEP 2: 商品明細ループの開始
        // ---------------------------------------------------------------
        // 目的: 明細単位の計算結果（税抜き金額・税額・重量・数量）を積算するための
        //       アキュムレータ変数を初期化し、メインループを開始する。
        // テスト観点: 明細0件・明細1件・明細複数件のケースを確認する。
        // ===================================================================
        BigDecimal subtotalAccumulator = BigDecimal.ZERO;
        BigDecimal taxAmountAccumulator = BigDecimal.ZERO;
        int totalWeightGramAccumulator = 0;
        int totalQuantityAccumulator = 0;
        int itemTypeCount = 0;

        for (OrderItem item : orderItems) {
            // ループ(1): 明細ごとに税抜き金額・税額・重量を積算するメインループ
            itemTypeCount = itemTypeCount + 1;
            calculationLog.append("STEP2: loop iteration. itemTypeCount=").append(itemTypeCount)
                    .append(", productId=").append(item.getProductId())
                    .append(", quantity=").append(item.getQuantity()).append("\n");

            Product product = productDao.findById(item.getProductId());
            if (product == null) {
                // 分岐(1-c): 明細が参照する商品が存在しない場合
                calculationLog.append("STEP2: product not found. productId=").append(item.getProductId()).append("\n");
                throw new IllegalArgumentException("商品が見つかりません: productId=" + item.getProductId());
            }

            String category = product.getCategory();
            BigDecimal categoryTaxRate;
            String categoryTaxRateReason;

            // ---------------------------------------------------------------
            // STEP 3: カテゴリ別税率判定
            // 目的: 商品カテゴリに応じた税率を確定する。
            // テスト観点: FOOD/BOOK/CLOTHING/ELECTRONICS/LUXURY/想定外カテゴリの
            //             6パターンそれぞれで税率が正しいことを確認する。
            // ---------------------------------------------------------------
            if ("FOOD".equals(category)) {
                // 分岐(2): 食品は軽減税率8%
                categoryTaxRate = new BigDecimal("0.08");
                categoryTaxRateReason = "FOOD:軽減税率8%";
            } else if ("BOOK".equals(category)) {
                // 分岐(3): 書籍も軽減税率8%
                categoryTaxRate = new BigDecimal("0.08");
                categoryTaxRateReason = "BOOK:軽減税率8%";
            } else if ("CLOTHING".equals(category)) {
                // 分岐(4): 衣類は標準税率10%
                categoryTaxRate = new BigDecimal("0.10");
                categoryTaxRateReason = "CLOTHING:標準税率10%";
            } else if ("ELECTRONICS".equals(category)) {
                // 分岐(5): 電子機器は標準税率10%
                categoryTaxRate = new BigDecimal("0.10");
                categoryTaxRateReason = "ELECTRONICS:標準税率10%";
            } else if ("LUXURY".equals(category)) {
                // 分岐(6): 贅沢品は標準税率10%＋贅沢税2%＝12%
                BigDecimal standardRate = new BigDecimal("0.10");
                BigDecimal luxurySurcharge = new BigDecimal("0.02");
                categoryTaxRate = standardRate.add(luxurySurcharge);
                categoryTaxRateReason = "LUXURY:標準税率10%+贅沢税2%";
            } else {
                // 想定外カテゴリは標準税率10%にフォールバック
                categoryTaxRate = new BigDecimal("0.10");
                categoryTaxRateReason = "UNKNOWN:標準税率10%にフォールバック";
            }
            calculationLog.append("STEP3: category=").append(category)
                    .append(", categoryTaxRate=").append(categoryTaxRate)
                    .append(" (").append(categoryTaxRateReason).append(")\n");

            BigDecimal unitPrice = new BigDecimal(item.getUnitPrice());
            BigDecimal taxExcludedUnitPrice;

            // ---------------------------------------------------------------
            // STEP 4: 内税/外税判定
            // 目的: 商品マスタの tax_included_flag に応じて税抜き単価を求める。
            // テスト観点: 内税商品・外税商品それぞれで税抜き単価の算出方法が
            //             異なることを確認する。
            // ---------------------------------------------------------------
            Boolean taxIncludedFlag = product.getTaxIncludedFlag();
            if (Boolean.TRUE.equals(taxIncludedFlag)) {
                // 分岐(7-a): 内税商品は単価から税額を逆算して税抜き単価を求める
                BigDecimal divisor = BigDecimal.ONE.add(categoryTaxRate);
                taxExcludedUnitPrice = unitPrice.divide(divisor, 4, RoundingMode.HALF_UP);
                calculationLog.append("STEP4: tax included. unitPrice=").append(unitPrice)
                        .append(", taxExcludedUnitPrice=").append(taxExcludedUnitPrice).append("\n");
            } else {
                // 分岐(7-b): 外税商品は単価がそのまま税抜き単価
                taxExcludedUnitPrice = unitPrice;
                calculationLog.append("STEP4: tax excluded. taxExcludedUnitPrice=").append(taxExcludedUnitPrice).append("\n");
            }

            int quantity = item.getQuantity();
            BigDecimal quantityDecimal = new BigDecimal(quantity);

            BigDecimal volumeDiscountRate;
            String volumeDiscountReason;

            // ---------------------------------------------------------------
            // STEP 5: 数量帯ボリュームディスカウント判定
            // 目的: 明細の数量に応じたボリュームディスカウント率を確定する。
            // テスト観点: 1-4個/5-9個/10-19個/20個以上の境界値を確認する。
            // ---------------------------------------------------------------
            if (quantity >= 20) {
                // 分岐(8): 20個以上は8%割引
                volumeDiscountRate = new BigDecimal("0.08");
                volumeDiscountReason = "20個以上:8%割引";
            } else if (quantity >= 10) {
                // 分岐(9): 10〜19個は5%割引
                volumeDiscountRate = new BigDecimal("0.05");
                volumeDiscountReason = "10-19個:5%割引";
            } else if (quantity >= 5) {
                // 分岐(10): 5〜9個は3%割引
                volumeDiscountRate = new BigDecimal("0.03");
                volumeDiscountReason = "5-9個:3%割引";
            } else {
                // 1〜4個は割引なし
                volumeDiscountRate = BigDecimal.ZERO;
                volumeDiscountReason = "1-4個:割引なし";
            }
            calculationLog.append("STEP5: quantity=").append(quantity)
                    .append(", volumeDiscountRate=").append(volumeDiscountRate)
                    .append(" (").append(volumeDiscountReason).append(")\n");

            // 明細単位の金額計算を中間変数に分解する（テスト時に各段階の値を追跡しやすくするため）
            BigDecimal lineGrossAmount = taxExcludedUnitPrice.multiply(quantityDecimal);
            BigDecimal volumeDiscountMultiplier = BigDecimal.ONE.subtract(volumeDiscountRate);
            BigDecimal lineNetAmount = lineGrossAmount.multiply(volumeDiscountMultiplier);
            BigDecimal lineDiscountAmount = lineGrossAmount.subtract(lineNetAmount);
            BigDecimal lineTaxAmount = lineNetAmount.multiply(categoryTaxRate);

            calculationLog.append("STEP5: lineGrossAmount=").append(lineGrossAmount)
                    .append(", lineDiscountAmount=").append(lineDiscountAmount)
                    .append(", lineNetAmount=").append(lineNetAmount)
                    .append(", lineTaxAmount=").append(lineTaxAmount).append("\n");

            int lineWeight = product.getWeightGram() * quantity;

            // ---------------------------------------------------------------
            // STEP 6: 明細小計・税額・重量・数量の累積
            // 目的: ループ内で算出した明細単位の値を、注文単位のアキュムレータへ
            //       積算する。
            // ---------------------------------------------------------------
            subtotalAccumulator = subtotalAccumulator.add(lineNetAmount);
            taxAmountAccumulator = taxAmountAccumulator.add(lineTaxAmount);
            totalWeightGramAccumulator = totalWeightGramAccumulator + lineWeight;
            totalQuantityAccumulator = totalQuantityAccumulator + quantity;

            calculationLog.append("STEP6: subtotalAccumulator=").append(subtotalAccumulator)
                    .append(", taxAmountAccumulator=").append(taxAmountAccumulator)
                    .append(", totalWeightGramAccumulator=").append(totalWeightGramAccumulator)
                    .append(", totalQuantityAccumulator=").append(totalQuantityAccumulator).append("\n");
        }

        BigDecimal subtotal = subtotalAccumulator;
        calculationLog.append("STEP6: loop finished. subtotal=").append(subtotal)
                .append(", itemTypeCount=").append(itemTypeCount).append("\n");

        // ===================================================================
        // STEP 7: 季節キャンペーン判定
        // ---------------------------------------------------------------
        // 目的: 注文月がウィンターセール(12月)またはサマーセール(7-8月)に
        //       該当するかを判定し、追加割引率とキャンペーンフラグを確定する。
        //       このフラグはSTEP17のポイント倍増判定でも再利用される。
        // テスト観点: 12月/7月/8月/その他月の4パターンを確認する。
        // ===================================================================
        boolean seasonalCampaignActive;
        BigDecimal seasonalDiscountRate;
        String seasonalReason;

        if (orderMonth == 12) {
            // 分岐(11-a): 12月はウィンターセール期間
            seasonalCampaignActive = true;
            seasonalDiscountRate = new BigDecimal("0.02");
            seasonalReason = "12月:ウィンターセール";
        } else if (orderMonth == 7 || orderMonth == 8) {
            // 分岐(11-b): 7〜8月はサマーセール期間
            seasonalCampaignActive = true;
            seasonalDiscountRate = new BigDecimal("0.02");
            seasonalReason = "7-8月:サマーセール";
        } else {
            // キャンペーン対象月でない
            seasonalCampaignActive = false;
            seasonalDiscountRate = BigDecimal.ZERO;
            seasonalReason = "キャンペーン対象月でない";
        }

        BigDecimal seasonalDiscountAmount = subtotal.multiply(seasonalDiscountRate);
        calculationLog.append("STEP7: seasonalCampaignActive=").append(seasonalCampaignActive)
                .append(", seasonalDiscountAmount=").append(seasonalDiscountAmount)
                .append(" (").append(seasonalReason).append(")\n");

        // ===================================================================
        // STEP 8: 会員ランク別割引判定
        // ---------------------------------------------------------------
        // 目的: 顧客の会員ランクに応じた割引率を確定する。
        // テスト観点: BRONZE/SILVER/GOLD/PLATINUMの4ランクを確認する。
        // ===================================================================
        String memberRank = customer.getMemberRank();
        BigDecimal rankDiscountRate;
        String rankDiscountReason;

        if ("PLATINUM".equals(memberRank)) {
            // 分岐(12-a): PLATINUM会員は6%割引
            rankDiscountRate = new BigDecimal("0.06");
            rankDiscountReason = "PLATINUM:6%割引";
        } else if ("GOLD".equals(memberRank)) {
            // 分岐(12-b): GOLD会員は4%割引
            rankDiscountRate = new BigDecimal("0.04");
            rankDiscountReason = "GOLD:4%割引";
        } else if ("SILVER".equals(memberRank)) {
            // 分岐(12-c): SILVER会員は2%割引
            rankDiscountRate = new BigDecimal("0.02");
            rankDiscountReason = "SILVER:2%割引";
        } else {
            // BRONZE会員は割引なし
            rankDiscountRate = BigDecimal.ZERO;
            rankDiscountReason = "BRONZE:割引なし";
        }

        BigDecimal rankDiscountAmount = subtotal.multiply(rankDiscountRate);
        calculationLog.append("STEP8: memberRank=").append(memberRank)
                .append(", rankDiscountAmount=").append(rankDiscountAmount)
                .append(" (").append(rankDiscountReason).append(")\n");

        // ===================================================================
        // STEP 9: クーポン判定
        // ---------------------------------------------------------------
        // 目的: 注文に設定されたクーポンコードを検証し、種別（固定額/率/送料無料）
        //       と有効期限に応じてクーポン割引額・送料無料フラグを確定する。
        // テスト観点: クーポンなし／FIXED／RATE／FREE_SHIPPING／期限切れの
        //             5パターンを確認する。
        // ===================================================================
        String couponCode = order.getCouponCode();
        BigDecimal couponDiscountAmount = BigDecimal.ZERO;
        boolean freeShippingFlag = false;

        if (couponCode != null && !couponCode.isEmpty()) {
            // 分岐(13): クーポンコードが設定されている場合のみクーポンマスタを参照
            Coupon coupon = orderDao.findCouponByCode(couponCode);
            calculationLog.append("STEP9: couponCode=").append(couponCode)
                    .append(", couponFound=").append(coupon != null).append("\n");

            if (coupon != null) {
                LocalDate validFrom = coupon.getValidFrom();
                LocalDate validTo = coupon.getValidTo();
                boolean isWithinValidPeriod = !orderDate.isBefore(validFrom) && !orderDate.isAfter(validTo);

                if (isWithinValidPeriod) {
                    // 分岐(14): 有効期限内のクーポンのみ種別判定を行う
                    String discountType = coupon.getDiscountType();
                    calculationLog.append("STEP9: coupon valid. discountType=").append(discountType).append("\n");

                    if ("FIXED".equals(discountType)) {
                        // 分岐(15-a): 固定額クーポン。小計を超えて割引しないようガードする
                        BigDecimal fixedValue = coupon.getDiscountValue();
                        if (fixedValue.compareTo(subtotal) > 0) {
                            couponDiscountAmount = subtotal;
                        } else {
                            couponDiscountAmount = fixedValue;
                        }
                    } else if ("RATE".equals(discountType)) {
                        // 分岐(15-b): 率クーポン
                        BigDecimal rateValue = coupon.getDiscountValue();
                        couponDiscountAmount = subtotal.multiply(rateValue);
                    } else if ("FREE_SHIPPING".equals(discountType)) {
                        // 分岐(15-c): 送料無料クーポン。金額割引はなく配送料フラグのみ立てる
                        freeShippingFlag = true;
                        couponDiscountAmount = BigDecimal.ZERO;
                    } else {
                        couponDiscountAmount = BigDecimal.ZERO;
                    }
                } else {
                    // 分岐(16): 有効期限切れのクーポンは無視する
                    calculationLog.append("STEP9: coupon expired. validFrom=").append(validFrom)
                            .append(", validTo=").append(validTo)
                            .append(", orderDate=").append(orderDate).append("\n");
                    couponDiscountAmount = BigDecimal.ZERO;
                }
            }
        } else {
            calculationLog.append("STEP9: no coupon code.\n");
        }
        calculationLog.append("STEP9: couponDiscountAmount=").append(couponDiscountAmount)
                .append(", freeShippingFlag=").append(freeShippingFlag).append("\n");

        // ===================================================================
        // STEP 10: 地域別基本配送料判定
        // ---------------------------------------------------------------
        // 目的: 顧客の配送地域に応じた基本配送料を確定する。
        // テスト観点: HOKKAIDO/OKINAWA/KANSAI/KANTO/その他の5パターンを確認する。
        // ===================================================================
        String region = customer.getRegion();
        BigDecimal regionShippingFee;
        String regionShippingReason;

        if ("HOKKAIDO".equals(region)) {
            // 分岐(17-a): 北海道は配送コストが高いため1000円
            regionShippingFee = new BigDecimal("1000");
            regionShippingReason = "HOKKAIDO:1000円";
        } else if ("OKINAWA".equals(region)) {
            // 分岐(17-b): 沖縄は配送コストが最も高いため1200円
            regionShippingFee = new BigDecimal("1200");
            regionShippingReason = "OKINAWA:1200円";
        } else if ("KANSAI".equals(region)) {
            // 分岐(17-c): 関西は600円
            regionShippingFee = new BigDecimal("600");
            regionShippingReason = "KANSAI:600円";
        } else if ("KANTO".equals(region)) {
            // 分岐(17-d): 関東は最も低コストで500円
            regionShippingFee = new BigDecimal("500");
            regionShippingReason = "KANTO:500円";
        } else {
            // その他地域は標準800円
            regionShippingFee = new BigDecimal("800");
            regionShippingReason = "OTHER:800円";
        }
        calculationLog.append("STEP10: region=").append(region)
                .append(", regionShippingFee=").append(regionShippingFee)
                .append(" (").append(regionShippingReason).append(")\n");

        // ===================================================================
        // STEP 11: 重量帯別追加配送料判定
        // ---------------------------------------------------------------
        // 目的: 注文全体の合計重量に応じた追加配送料を確定する。
        // テスト観点: 0-1000g/1000-5000g/5000-10000g/10000g超の境界値を確認する。
        // ===================================================================
        BigDecimal weightShippingFee;
        String weightShippingReason;

        if (totalWeightGramAccumulator > 10000) {
            // 分岐(18-a): 10kg超は追加1000円
            weightShippingFee = new BigDecimal("1000");
            weightShippingReason = "10kg超:追加1000円";
        } else if (totalWeightGramAccumulator > 5000) {
            // 分岐(18-b): 5kg超10kg以下は追加600円
            weightShippingFee = new BigDecimal("600");
            weightShippingReason = "5kg超10kg以下:追加600円";
        } else if (totalWeightGramAccumulator > 1000) {
            // 分岐(18-c): 1kg超5kg以下は追加300円
            weightShippingFee = new BigDecimal("300");
            weightShippingReason = "1kg超5kg以下:追加300円";
        } else {
            // 1kg以下は追加料金なし
            weightShippingFee = BigDecimal.ZERO;
            weightShippingReason = "1kg以下:追加なし";
        }
        calculationLog.append("STEP11: totalWeightGram=").append(totalWeightGramAccumulator)
                .append(", weightShippingFee=").append(weightShippingFee)
                .append(" (").append(weightShippingReason).append(")\n");

        BigDecimal baseShippingFee = regionShippingFee.add(weightShippingFee);
        calculationLog.append("STEP11: baseShippingFee=").append(baseShippingFee).append("\n");

        // ===================================================================
        // STEP 12: 配送料無料判定
        // ---------------------------------------------------------------
        // 目的: 割引後小計が1万円以上、またはFREE_SHIPPINGクーポン適用時に
        //       配送料を0円にする。
        // テスト観点: 閾値ちょうど・閾値未満・FREE_SHIPPING併用の3パターンを
        //             確認する。
        // ===================================================================
        BigDecimal subtotalAfterProductDiscounts = subtotal
                .subtract(seasonalDiscountAmount)
                .subtract(rankDiscountAmount)
                .subtract(couponDiscountAmount);
        calculationLog.append("STEP12: subtotalAfterProductDiscounts=").append(subtotalAfterProductDiscounts).append("\n");

        BigDecimal freeShippingThreshold = new BigDecimal("10000");
        BigDecimal shippingFee;

        if (subtotalAfterProductDiscounts.compareTo(freeShippingThreshold) >= 0) {
            // 分岐(19-a): 割引後小計が1万円以上なら配送料無料
            shippingFee = BigDecimal.ZERO;
            calculationLog.append("STEP12: free shipping by amount threshold.\n");
        } else if (freeShippingFlag) {
            // 分岐(19-b): FREE_SHIPPINGクーポン適用時も配送料無料
            shippingFee = BigDecimal.ZERO;
            calculationLog.append("STEP12: free shipping by coupon.\n");
        } else {
            shippingFee = baseShippingFee;
            calculationLog.append("STEP12: shippingFee charged. shippingFee=").append(shippingFee).append("\n");
        }

        // ===================================================================
        // STEP 13: 支払方法別手数料判定
        // ---------------------------------------------------------------
        // 目的: 支払方法に応じた決済手数料を確定する。COD（代引き）は
        //       暫定合計の金額帯によって手数料が変動する。
        // テスト観点: CREDIT_CARD/BANK_TRANSFER/POINT/COD(低額)/COD(高額)の
        //             5パターンを確認する。
        // ===================================================================
        // 手数料の金額帯判定に使う暫定合計（手数料自体は含まない）
        BigDecimal provisionalTotalBeforeFee = subtotalAfterProductDiscounts
                .add(taxAmountAccumulator)
                .add(shippingFee);
        calculationLog.append("STEP13: provisionalTotalBeforeFee=").append(provisionalTotalBeforeFee).append("\n");

        String paymentMethod = order.getPaymentMethod();
        BigDecimal paymentFee;

        if ("CREDIT_CARD".equals(paymentMethod)) {
            // 分岐(20-a): クレジットカードは手数料なし
            paymentFee = BigDecimal.ZERO;
        } else if ("BANK_TRANSFER".equals(paymentMethod)) {
            // 分岐(20-b): 銀行振込は固定200円
            paymentFee = new BigDecimal("200");
        } else if ("POINT".equals(paymentMethod)) {
            // 分岐(20-c): ポイント支払いは手数料なし
            paymentFee = BigDecimal.ZERO;
        } else if ("COD".equals(paymentMethod)) {
            // 分岐(21): 代引きは金額帯で手数料が変動する
            BigDecimal codHighAmountThreshold = new BigDecimal("10000");
            if (provisionalTotalBeforeFee.compareTo(codHighAmountThreshold) >= 0) {
                paymentFee = new BigDecimal("500");
                calculationLog.append("STEP13: COD high amount fee.\n");
            } else {
                paymentFee = new BigDecimal("300");
                calculationLog.append("STEP13: COD low amount fee.\n");
            }
        } else {
            paymentFee = BigDecimal.ZERO;
        }
        calculationLog.append("STEP13: paymentMethod=").append(paymentMethod)
                .append(", paymentFee=").append(paymentFee).append("\n");

        // ===================================================================
        // STEP 14: 誕生月特典判定
        // ---------------------------------------------------------------
        // 目的: 注文月が顧客の誕生月と一致する場合にボーナスポイントを加算する。
        // テスト観点: 誕生月一致／不一致の2パターンを確認する。
        // ===================================================================
        int birthdayBonusPoints;
        Integer birthMonth = customer.getBirthMonth();

        if (birthMonth != null && birthMonth.intValue() == orderMonth) {
            // 分岐(22): 注文月が顧客の誕生月と一致した場合、ボーナスポイントを加算
            birthdayBonusPoints = 300;
            calculationLog.append("STEP14: birthday month matched. bonusPoints=300\n");
        } else {
            birthdayBonusPoints = 0;
            calculationLog.append("STEP14: birthday month not matched.\n");
        }

        // ===================================================================
        // STEP 15: 初回注文特典判定
        // ---------------------------------------------------------------
        // 目的: 初回注文の顧客に小計の5%を追加割引する。
        // テスト観点: firstOrderFlag=true/falseの2パターンを確認する。
        // ===================================================================
        BigDecimal firstOrderDiscountAmount;
        Boolean firstOrderFlag = customer.getFirstOrderFlag();

        if (Boolean.TRUE.equals(firstOrderFlag)) {
            // 分岐(23): 初回注文の顧客は小計の5%を追加割引
            BigDecimal firstOrderDiscountRate = new BigDecimal("0.05");
            firstOrderDiscountAmount = subtotal.multiply(firstOrderDiscountRate);
            calculationLog.append("STEP15: first order discount applied. amount=").append(firstOrderDiscountAmount).append("\n");
        } else {
            firstOrderDiscountAmount = BigDecimal.ZERO;
            calculationLog.append("STEP15: not first order.\n");
        }

        // ===================================================================
        // STEP 16: 大量注文特典判定
        // ---------------------------------------------------------------
        // 目的: 明細種類数が3以上、または合計数量が15以上の場合に
        //       追加500円の割引を行う。
        // テスト観点: 種類数のみ条件成立／数量のみ条件成立／両方不成立の
        //             3パターンを確認する。
        // ===================================================================
        BigDecimal bulkOrderDiscountAmount;
        boolean manyItemTypes = itemTypeCount >= 3;
        boolean manyQuantity = totalQuantityAccumulator >= 15;
        calculationLog.append("STEP16: manyItemTypes=").append(manyItemTypes)
                .append(", manyQuantity=").append(manyQuantity).append("\n");

        if (manyItemTypes || manyQuantity) {
            // 分岐(24): 明細種類数が3以上、または合計数量が15以上なら追加500円割引
            bulkOrderDiscountAmount = new BigDecimal("500");
            calculationLog.append("STEP16: bulk order discount applied.\n");
        } else {
            bulkOrderDiscountAmount = BigDecimal.ZERO;
            calculationLog.append("STEP16: no bulk order discount.\n");
        }

        BigDecimal bonusDiscountAmount = firstOrderDiscountAmount.add(bulkOrderDiscountAmount);

        BigDecimal totalDiscountBeforeRounding = seasonalDiscountAmount
                .add(rankDiscountAmount)
                .add(couponDiscountAmount)
                .add(bonusDiscountAmount);
        calculationLog.append("STEP16: totalDiscountBeforeRounding=").append(totalDiscountBeforeRounding).append("\n");

        // ===================================================================
        // STEP 17: ポイント計算
        // ---------------------------------------------------------------
        // 目的: ランク別倍率テーブルをループ検索し、確定金額に対するポイントを
        //       算出する。季節キャンペーン中はポイントを倍増する。
        // テスト観点: 4ランクそれぞれのポイント倍率、キャンペーン中/外での
        //             倍増有無を確認する。
        // ===================================================================
        String[] rankKeys = {"BRONZE", "SILVER", "GOLD", "PLATINUM"};
        BigDecimal[] rankPointRates = {
                new BigDecimal("0.01"),
                new BigDecimal("0.015"),
                new BigDecimal("0.02"),
                new BigDecimal("0.03")
        };

        BigDecimal matchedPointRate = BigDecimal.ZERO;
        for (int rankIndex = 0; rankIndex < rankKeys.length; rankIndex++) {
            // ループ(2): ランク別ポイント倍率テーブルを先頭から検索する
            calculationLog.append("STEP17: scanning rank table. index=").append(rankIndex)
                    .append(", key=").append(rankKeys[rankIndex]).append("\n");
            if (rankKeys[rankIndex].equals(memberRank)) {
                // 分岐(25): 一致したランクの倍率を採用し検索を打ち切る
                matchedPointRate = rankPointRates[rankIndex];
                calculationLog.append("STEP17: rank matched. pointRate=").append(matchedPointRate).append("\n");
                break;
            }
        }

        BigDecimal pointBaseAmount = subtotal.subtract(totalDiscountBeforeRounding);
        if (pointBaseAmount.compareTo(BigDecimal.ZERO) < 0) {
            pointBaseAmount = BigDecimal.ZERO;
        }
        calculationLog.append("STEP17: pointBaseAmount=").append(pointBaseAmount).append("\n");

        BigDecimal earnedPointsDecimal = pointBaseAmount.multiply(matchedPointRate);
        if (seasonalCampaignActive) {
            // 季節キャンペーン中はポイントを倍増
            earnedPointsDecimal = earnedPointsDecimal.multiply(new BigDecimal("2"));
            calculationLog.append("STEP17: points doubled by seasonal campaign.\n");
        }

        int earnedPoints = earnedPointsDecimal.setScale(0, RoundingMode.DOWN).intValue() + birthdayBonusPoints;
        calculationLog.append("STEP17: earnedPoints=").append(earnedPoints).append("\n");

        // ===================================================================
        // STEP 18: ラウンディング処理
        // ---------------------------------------------------------------
        // 目的: 税額には四捨五入、割引合計には切り捨てという異なる丸めルールを
        //       適用し、最終的な金額確定に使う値を確定する。
        // テスト観点: 端数が生じるケースで丸め方向が仕様通りであることを確認する。
        // ===================================================================
        // 分岐(26): 税額は四捨五入、割引合計は切り捨てという異なるルールを適用する
        BigDecimal roundedTaxAmount = taxAmountAccumulator.setScale(0, RoundingMode.HALF_UP);
        BigDecimal roundedTotalDiscount = totalDiscountBeforeRounding.setScale(0, RoundingMode.DOWN);
        calculationLog.append("STEP18: roundedTaxAmount=").append(roundedTaxAmount)
                .append(", roundedTotalDiscount=").append(roundedTotalDiscount).append("\n");

        // ===================================================================
        // STEP 19: 合計金額確定
        // ---------------------------------------------------------------
        // 目的: 小計・割引・税額・配送料・決済手数料から最終合計金額を算出し、
        //       負数にならないようガードする。
        // テスト観点: 割引が大きく合計が0円未満になり得るケースを確認する。
        // ===================================================================
        BigDecimal totalAmount = subtotal
                .subtract(roundedTotalDiscount)
                .add(roundedTaxAmount)
                .add(shippingFee)
                .add(paymentFee);
        calculationLog.append("STEP19: totalAmount(before guard)=").append(totalAmount).append("\n");

        if (totalAmount.compareTo(BigDecimal.ZERO) < 0) {
            // 分岐(27): 割引が金額を上回るケースで合計が負数にならないようガードする
            calculationLog.append("STEP19: totalAmount guarded to zero.\n");
            totalAmount = BigDecimal.ZERO;
        }

        // ===================================================================
        // STEP 20: 結果オブジェクトの構築
        // ---------------------------------------------------------------
        // 目的: 各STEPで確定した値を OrderCalculationResult に詰め替えて返す。
        // ===================================================================
        OrderCalculationResult result = new OrderCalculationResult();
        result.setOrder(order);
        result.setSubtotal(subtotal.setScale(0, RoundingMode.HALF_UP));
        result.setTotalDiscount(roundedTotalDiscount);
        result.setTaxAmount(roundedTaxAmount);
        result.setShippingFee(shippingFee);
        result.setPaymentFee(paymentFee);
        result.setBonusDiscount(bonusDiscountAmount.setScale(0, RoundingMode.DOWN));
        result.setTotalAmount(totalAmount.setScale(0, RoundingMode.HALF_UP));
        result.setEarnedPoints(earnedPoints);

        calculationLog.append("STEP20: result built. totalAmount=").append(result.getTotalAmount())
                .append(", earnedPoints=").append(result.getEarnedPoints()).append("\n");
        System.out.println(calculationLog);

        return result;
    }
}
