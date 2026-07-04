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
import com.example.testsampleapp.model.Product;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderCalculationServiceImplTest {

    @Mock
    private OrderDao orderDao;

    @Mock
    private OrderItemDao orderItemDao;

    @Mock
    private CustomerDao customerDao;

    @Mock
    private ProductDao productDao;

    @InjectMocks
    private OrderCalculationServiceImpl orderCalculationService;

    @Test
    void calculateOrderAmount_注文が存在しない場合は例外を投げる() {
        when(orderDao.findById(999)).thenReturn(null);

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> orderCalculationService.calculateOrderAmount(999));
        assertTrue(ex.getMessage().contains("999"));
    }

    @Test
    void calculateOrderAmount_顧客が存在しない場合は例外を投げる() {
        Order order = new Order();
        order.setId(1);
        order.setCustomerId(100);
        when(orderDao.findById(1)).thenReturn(order);
        when(customerDao.findById(100)).thenReturn(null);

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> orderCalculationService.calculateOrderAmount(1));
        assertTrue(ex.getMessage().contains("100"));
    }

    @Test
    void calculateOrderAmount_商品が存在しない場合は例外を投げる() {
        Order order = new Order();
        order.setId(1);
        order.setCustomerId(100);
        order.setOrderDate(LocalDate.of(2026, 3, 10));
        when(orderDao.findById(1)).thenReturn(order);

        Customer customer = new Customer();
        customer.setId(100);
        customer.setMemberRank("BRONZE");
        customer.setRegion("KANTO");
        when(customerDao.findById(100)).thenReturn(customer);

        OrderItem item = new OrderItem();
        item.setProductId(10);
        item.setQuantity(1);
        item.setUnitPrice(1000);
        when(orderItemDao.findByOrderId(1)).thenReturn(Collections.singletonList(item));

        when(productDao.findById(10)).thenReturn(null);

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> orderCalculationService.calculateOrderAmount(1));
        assertTrue(ex.getMessage().contains("10"));
    }

    @Test
    void calculateOrderAmount_基本ケースで金額とポイントが正しく計算される() {
        Order order = new Order();
        order.setId(1);
        order.setCustomerId(100);
        order.setOrderDate(LocalDate.of(2026, 3, 10));
        order.setCouponCode(null);
        order.setPaymentMethod("CREDIT_CARD");
        when(orderDao.findById(1)).thenReturn(order);

        Customer customer = new Customer();
        customer.setId(100);
        customer.setMemberRank("BRONZE");
        customer.setRegion("KANTO");
        customer.setBirthMonth(5);
        customer.setFirstOrderFlag(false);
        when(customerDao.findById(100)).thenReturn(customer);

        OrderItem item = new OrderItem();
        item.setProductId(10);
        item.setQuantity(2);
        item.setUnitPrice(1000);
        when(orderItemDao.findByOrderId(1)).thenReturn(Collections.singletonList(item));

        Product product = new Product();
        product.setId(10);
        product.setCategory("FOOD");
        product.setTaxIncludedFlag(false);
        product.setWeightGram(100);
        when(productDao.findById(10)).thenReturn(product);

        OrderCalculationResult result = orderCalculationService.calculateOrderAmount(1);

        assertEquals(new BigDecimal("2000"), result.getSubtotal());
        assertEquals(new BigDecimal("0"), result.getTotalDiscount());
        assertEquals(new BigDecimal("160"), result.getTaxAmount());
        assertEquals(new BigDecimal("500"), result.getShippingFee());
        assertEquals(new BigDecimal("0"), result.getPaymentFee());
        assertEquals(new BigDecimal("0"), result.getBonusDiscount());
        assertEquals(new BigDecimal("2660"), result.getTotalAmount());
        assertEquals(20, result.getEarnedPoints());
    }

    @Test
    void calculateOrderAmount_複合ケースでキャンペーンとクーポンと大量注文割引が反映される() {
        Order order = new Order();
        order.setId(1);
        order.setCustomerId(100);
        order.setOrderDate(LocalDate.of(2026, 12, 15));
        order.setCouponCode("FIXEDCOUPON");
        order.setPaymentMethod("COD");
        when(orderDao.findById(1)).thenReturn(order);

        Customer customer = new Customer();
        customer.setId(100);
        customer.setMemberRank("GOLD");
        customer.setRegion("OKINAWA");
        customer.setBirthMonth(12);
        customer.setFirstOrderFlag(true);
        when(customerDao.findById(100)).thenReturn(customer);

        OrderItem item1 = new OrderItem();
        item1.setProductId(10);
        item1.setQuantity(5);
        item1.setUnitPrice(1000);
        OrderItem item2 = new OrderItem();
        item2.setProductId(11);
        item2.setQuantity(5);
        item2.setUnitPrice(1000);
        OrderItem item3 = new OrderItem();
        item3.setProductId(12);
        item3.setQuantity(5);
        item3.setUnitPrice(1000);
        List<OrderItem> items = Arrays.asList(item1, item2, item3);
        when(orderItemDao.findByOrderId(1)).thenReturn(items);

        Product product = new Product();
        product.setCategory("CLOTHING");
        product.setTaxIncludedFlag(false);
        product.setWeightGram(2000);
        when(productDao.findById(10)).thenReturn(product);
        when(productDao.findById(11)).thenReturn(product);
        when(productDao.findById(12)).thenReturn(product);

        Coupon coupon = new Coupon();
        coupon.setCode("FIXEDCOUPON");
        coupon.setDiscountType("FIXED");
        coupon.setDiscountValue(new BigDecimal("500"));
        coupon.setValidFrom(LocalDate.of(2026, 12, 1));
        coupon.setValidTo(LocalDate.of(2026, 12, 31));
        when(orderDao.findCouponByCode("FIXEDCOUPON")).thenReturn(coupon);

        OrderCalculationResult result = orderCalculationService.calculateOrderAmount(1);

        assertEquals(new BigDecimal("14550"), result.getSubtotal());
        assertEquals(new BigDecimal("2600"), result.getTotalDiscount());
        assertEquals(new BigDecimal("1455"), result.getTaxAmount());
        assertEquals(new BigDecimal("0"), result.getShippingFee());
        assertEquals(new BigDecimal("500"), result.getPaymentFee());
        assertEquals(new BigDecimal("1227"), result.getBonusDiscount());
        assertEquals(new BigDecimal("13905"), result.getTotalAmount());
        assertEquals(777, result.getEarnedPoints());
    }
}
