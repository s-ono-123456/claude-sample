package com.example.sampleapp.dao;

import com.example.sampleapp.model.Order;
import com.example.sampleapp.model.OrderItem;
import org.apache.ibatis.annotations.Mapper;
import java.util.List;

@Mapper
public interface OrderDao {
    List<Order> findByUserId(Integer userId);
    Order findById(Integer id);
    int insertOrder(Order order);
    int insertOrderItem(OrderItem item);
    int updateOrderStatus(Integer id, String status);
    List<OrderItem> findItemsByOrderId(Integer orderId);
}
