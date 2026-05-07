package com.example.sampleapp.service;

import com.example.sampleapp.dao.OrderDao;
import com.example.sampleapp.model.Order;
import com.example.sampleapp.model.OrderItem;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
public class OrderServiceImpl implements OrderService {

    @Autowired
    private OrderDao orderDao;

    @Autowired
    private ProductService productService;

    @Override
    public List<Order> getOrdersByUserId(Integer userId) {
        return orderDao.findByUserId(userId);
    }

    @Override
    public Order getOrderById(Integer id) {
        Order order = orderDao.findById(id);
        if (order != null) {
            List<OrderItem> items = orderDao.findItemsByOrderId(id);
            order.setItems(items);
        }
        return order;
    }

    @Override
    @Transactional
    public void placeOrder(Order order) {
        for (OrderItem item : order.getItems()) {
            if (!productService.checkStock(item.getProductId(), item.getQuantity())) {
                throw new RuntimeException("在庫不足: productId=" + item.getProductId());
            }
        }
        orderDao.insertOrder(order);
        for (OrderItem item : order.getItems()) {
            item.setOrderId(order.getId());
            orderDao.insertOrderItem(item);
            productService.decreaseStock(item.getProductId(), item.getQuantity());
        }
    }

    @Override
    @Transactional
    public void cancelOrder(Integer id) {
        orderDao.updateOrderStatus(id, "CANCELLED");
    }

    @Override
    @Transactional
    public void completeOrder(Integer id) {
        orderDao.updateOrderStatus(id, "COMPLETED");
    }
}
