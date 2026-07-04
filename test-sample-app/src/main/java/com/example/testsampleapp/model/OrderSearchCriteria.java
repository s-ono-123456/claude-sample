package com.example.testsampleapp.model;

import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDate;

public class OrderSearchCriteria {
    private String customerName;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate orderDateFrom;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate orderDateTo;

    private String memberRank;

    public String getCustomerName() { return customerName; }
    public void setCustomerName(String customerName) { this.customerName = customerName; }

    public LocalDate getOrderDateFrom() { return orderDateFrom; }
    public void setOrderDateFrom(LocalDate orderDateFrom) { this.orderDateFrom = orderDateFrom; }

    public LocalDate getOrderDateTo() { return orderDateTo; }
    public void setOrderDateTo(LocalDate orderDateTo) { this.orderDateTo = orderDateTo; }

    public String getMemberRank() { return memberRank; }
    public void setMemberRank(String memberRank) { this.memberRank = memberRank; }
}
