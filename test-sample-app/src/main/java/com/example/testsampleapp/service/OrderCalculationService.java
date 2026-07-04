package com.example.testsampleapp.service;

import com.example.testsampleapp.model.Order;
import com.example.testsampleapp.model.OrderCalculationResult;
import com.example.testsampleapp.model.OrderSearchCriteria;

import java.util.List;

public interface OrderCalculationService {
    List<Order> searchOrders(OrderSearchCriteria criteria);
    OrderCalculationResult calculateOrderAmount(Integer orderId);
}
