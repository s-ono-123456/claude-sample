package com.example.testsampleapp.dao;

import com.example.testsampleapp.model.OrderItem;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface OrderItemDao {
    List<OrderItem> findByOrderId(Integer orderId);
}
