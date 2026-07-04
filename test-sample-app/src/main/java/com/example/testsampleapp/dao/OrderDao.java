package com.example.testsampleapp.dao;

import com.example.testsampleapp.model.Coupon;
import com.example.testsampleapp.model.Order;
import com.example.testsampleapp.model.OrderSearchCriteria;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface OrderDao {
    List<Order> search(OrderSearchCriteria criteria);
    Order findById(Integer id);
    Coupon findCouponByCode(String code);
}
