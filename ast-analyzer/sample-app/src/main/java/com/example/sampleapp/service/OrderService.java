package com.example.sampleapp.service;

import com.example.sampleapp.model.Order;
import java.util.List;

public interface OrderService {
    List<Order> getOrdersByUserId(Integer userId);
    Order getOrderById(Integer id);
    void placeOrder(Order order);
    void cancelOrder(Integer id);
    void completeOrder(Integer id);
}
