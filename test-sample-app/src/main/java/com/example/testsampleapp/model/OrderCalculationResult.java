package com.example.testsampleapp.model;

import java.math.BigDecimal;

public class OrderCalculationResult {
    private Order order;
    private BigDecimal subtotal;
    private BigDecimal totalDiscount;
    private BigDecimal taxAmount;
    private BigDecimal shippingFee;
    private BigDecimal paymentFee;
    private BigDecimal bonusDiscount;
    private BigDecimal totalAmount;
    private Integer earnedPoints;

    public Order getOrder() { return order; }
    public void setOrder(Order order) { this.order = order; }

    public BigDecimal getSubtotal() { return subtotal; }
    public void setSubtotal(BigDecimal subtotal) { this.subtotal = subtotal; }

    public BigDecimal getTotalDiscount() { return totalDiscount; }
    public void setTotalDiscount(BigDecimal totalDiscount) { this.totalDiscount = totalDiscount; }

    public BigDecimal getTaxAmount() { return taxAmount; }
    public void setTaxAmount(BigDecimal taxAmount) { this.taxAmount = taxAmount; }

    public BigDecimal getShippingFee() { return shippingFee; }
    public void setShippingFee(BigDecimal shippingFee) { this.shippingFee = shippingFee; }

    public BigDecimal getPaymentFee() { return paymentFee; }
    public void setPaymentFee(BigDecimal paymentFee) { this.paymentFee = paymentFee; }

    public BigDecimal getBonusDiscount() { return bonusDiscount; }
    public void setBonusDiscount(BigDecimal bonusDiscount) { this.bonusDiscount = bonusDiscount; }

    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal totalAmount) { this.totalAmount = totalAmount; }

    public Integer getEarnedPoints() { return earnedPoints; }
    public void setEarnedPoints(Integer earnedPoints) { this.earnedPoints = earnedPoints; }
}
